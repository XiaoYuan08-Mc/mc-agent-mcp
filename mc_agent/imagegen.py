"""生成式图像：多 provider 适配层。

本实现不绑死单一网关，按 provider 走公开端点或本地服务，
服务一断整条链路就死。这里改成**可换后端**：

| provider | 需要什么 | 说明 |
| --- | --- | --- |
| `pollinations` | 无 | 免费公开端点，每 IP 45 秒 1 张；有 `POLLINATIONS_TOKEN` 则不限期 |
| `openai` | `OPENAI_API_KEY`（可选 `OPENAI_BASE_URL`） | 兼容一切 OpenAI 风格图片接口（含国内多数中转） |
| `sdwebui` | 本地 SD WebUI 跑在 `SDWEBUI_URL`（默认 7860） | `/sdapi/v1/txt2img`，可控 steps/cfg |
| `comfyui` | 本地 ComfyUI（`COMFYUI_URL`，默认 8188） | 走默认 workflow 的 txt2img |

`auto` 按上表顺序探测环境变量，都不满足时回落到 pollinations（慢但能出图）。

只依赖标准库（urllib），不引进新的三方包。
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from mc_craft_mcp import config
from . import state


class ImageGenError(RuntimeError):
    pass


DEFAULT_TIMEOUT = 180


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def providers() -> dict:
    """探测本机可用的后端（不联网，只看配置与端口）。"""
    out = {
        "pollinations": {"ready": True, "free": True,
                         "needs": "无（每 IP 45s/张；高峰会 503，需重试）"},
        "openai": {"ready": bool(_env("OPENAI_API_KEY")),
                   "needs": "OPENAI_API_KEY（可选 OPENAI_BASE_URL / OPENAI_IMAGE_MODEL）"},
        "sdwebui": {"ready": bool(_probe(_env("SDWEBUI_URL", "http://127.0.0.1:7860") + "/sdapi/v1/progress")),
                    "needs": "本地 SD WebUI 开启 --api"},
        "comfyui": {"ready": bool(_probe(_env("COMFYUI_URL", "http://127.0.0.1:8188") + "/system_stats")),
                    "needs": "本地 ComfyUI 运行中"},
        "meshy": {"ready": bool(_env("MESHY_API_KEY")), "needs": "MESHY_API_KEY（3D，不是 2D）"},
    }
    for name, row in out.items():
        row["provider"] = name
    return out


def _probe(url: str, timeout: float = 1.2) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise ImageGenError(f"{url} 返回 {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ImageGenError(f"连不上 {url}: {exc.reason}") from exc


def _get_bytes(url: str, timeout: float, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise ImageGenError(f"{url} 返回 {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ImageGenError(f"连不上 {url}: {exc.reason}") from exc


def _save(raw: bytes, out: Path, size: int | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.open(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise ImageGenError(f"返回的不是图片（{len(raw)} 字节）: {exc}") from exc
    img = img.convert("RGBA")
    if size:
        # 像素资产：最近邻缩小后再量化，避免抗锯齿留下几百个过渡色
        img = img.resize((size, size), Image.NEAREST)
        img = img.quantize(colors=48, method=Image.FASTOCTREE).convert("RGBA")
    img.save(out)
    colors = img.getcolors(maxcolors=1 << 22) or []
    return {"output": str(out), "size": list(img.size), "unique_colors": len(colors)}


# --------------------------------------------------------------- providers
def _pollinations(prompt: str, w: int, h: int, seed: int, timeout: float) -> bytes:
    q = urllib.parse.quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&nologo=true"
    if seed:
        url += f"&seed={int(seed)}"
    token = _env("POLLINATIONS_TOKEN")
    if token:
        url += "&token=" + urllib.parse.quote(token)
    try:
        return _get_bytes(url, timeout)
    except ImageGenError as exc:
        msg = str(exc)
        if "FREE_LIMIT" in msg or "402" in msg:
            raise ImageGenError(
                "pollinations 免费额度到了（每 IP 45 秒 1 张，且日内有总量上限）。"
                "等一会儿再试，或设置 POLLINATIONS_TOKEN / 换 openai / 本地 SD WebUI。原始信息：" + msg[:200]
            ) from exc
        raise


def _openai(prompt: str, w: int, h: int, timeout: float, negative: str = "") -> bytes:
    key = _env("OPENAI_API_KEY")
    if not key:
        raise ImageGenError("没有 OPENAI_API_KEY")
    base = _env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = _env("OPENAI_IMAGE_MODEL", "gpt-image-1")
    size = f"{w}x{h}"
    payload = {"model": model, "prompt": prompt, "n": 1, "size": size}
    if model.startswith("dall-e"):
        payload["response_format"] = "b64_json"
    data = _post_json(f"{base}/images/generations", payload,
                      {"Authorization": f"Bearer {key}"}, timeout)
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return _get_bytes(item["url"], timeout)
    raise ImageGenError(f"OpenAI 风格返回里没有图片: {json.dumps(data)[:300]}")


def _sdwebui(prompt: str, w: int, h: int, seed: int, timeout: float,
             negative: str = "", steps: int = 24, cfg: float = 7.0) -> bytes:
    base = _env("SDWEBUI_URL", "http://127.0.0.1:7860").rstrip("/")
    payload = {
        "prompt": prompt, "negative_prompt": negative or "",
        "width": w, "height": h, "steps": steps, "cfg_scale": cfg,
        "seed": int(seed) if seed else -1, "batch_size": 1, "n_iter": 1,
    }
    data = _post_json(f"{base}/sdapi/v1/txt2img", payload, {}, timeout)
    images = data.get("images") or []
    if not images:
        raise ImageGenError("SD WebUI 没返回图片")
    raw = images[0]
    return base64.b64decode(raw.split(",", 1)[1] if raw.startswith("data:") else raw)


def _comfyui(prompt: str, w: int, h: int, seed: int, timeout: float, negative: str = "") -> bytes:
    """最小 txt2img 工作流，输出节点 id=9。只对默认 checkpoint 名做替换。"""
    base = _env("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
    ckpt = _env("COMFYUI_CHECKPOINT", "sd_xl_base_1.0.safetensors")
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": int(seed) or int(time.time()) % 2 ** 31, "steps": 24, "cfg": 7,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
            "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
            "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "", "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "mcagent", "images": ["8", 0]}},
    }
    data = _post_json(f"{base}/prompt", {"prompt": workflow}, {}, timeout)
    pid = data.get("prompt_id")
    if not pid:
        raise ImageGenError(f"ComfyUI 没给 prompt_id: {json.dumps(data)[:300]}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.5)
        hist = json.loads(_get_bytes(f"{base}/history/{pid}", 15).decode() or "{}")
        entry = hist.get(pid) or {}
        outputs = entry.get("outputs") or {}
        for node in outputs.values():
            for img in node.get("images") or []:
                qs = urllib.parse.urlencode({"filename": img["filename"],
                                             "subfolder": img.get("subfolder", ""),
                                             "type": img.get("type", "output")})
                return _get_bytes(f"{base}/view?{qs}", 60)
    raise ImageGenError("ComfyUI 超时，没等到图")


BACKENDS = {
    "pollinations": _pollinations,
    "openai": _openai,
    "sdwebui": _sdwebui,
    "comfyui": _comfyui,
}


def _pick(provider: str) -> str:
    p = (provider or "auto").lower()
    if p != "auto":
        if p not in BACKENDS:
            raise ImageGenError(f"未知 provider: {p}；可选 {sorted(BACKENDS)} 或 auto")
        return p
    if _env("OPENAI_API_KEY"):
        return "openai"
    if _probe(_env("SDWEBUI_URL", "http://127.0.0.1:7860") + "/sdapi/v1/progress"):
        return "sdwebui"
    if _probe(_env("COMFYUI_URL", "http://127.0.0.1:8188") + "/system_stats"):
        return "comfyui"
    return "pollinations"


def generate(prompt: str, out_path: str = "", width: int = 512, height: int = 512,
             provider: str = "auto", seed: int = 0, negative: str = "",
             pixel_size: int = 0, timeout: float = DEFAULT_TIMEOUT,
             retries: int = 2) -> dict:
    """出图并落盘。pixel_size>0 时按最近邻缩到该边长（像素风资产用）。"""
    if not prompt.strip():
        raise ImageGenError("prompt 为空")
    w = max(64, min(1536, int(width)))
    h = max(64, min(1536, int(height)))
    backend = _pick(provider)
    out = Path(out_path).expanduser().resolve() if out_path else \
        config.exports_dir() / f"gen_{state.new_id('img')}.png"

    last_error = None
    for attempt in range(max(0, retries) + 1):
        try:
            if backend == "openai":
                raw = _openai(prompt, w, h, timeout, negative)
            elif backend == "sdwebui":
                raw = _sdwebui(prompt, w, h, seed, timeout, negative)
            elif backend == "comfyui":
                raw = _comfyui(prompt, w, h, seed, timeout, negative)
            else:
                raw = _pollinations(prompt, w, h, seed, timeout)
            saved = _save(raw, out, pixel_size or None)
            return {
                "provider": backend,
                "prompt": prompt,
                "requested_size": [w, h],
                **saved,
                "pixel_size": pixel_size or None,
                "attempts": attempt + 1,
            }
        except ImageGenError as exc:
            last_error = exc
            msg = str(exc)
            if backend != "pollinations":
                break
            if "FREE_LIMIT" in msg or "402" in msg:
                wait = 46          # 免费档：每 IP 45 秒 1 张
            elif "503" in msg or "SERVICE_UNAVAILABLE" in msg:
                wait = 12          # 公共端点临时打满，通常 10 秒恢复
            else:
                break
            if attempt < max(0, retries):
                time.sleep(wait)
    raise ImageGenError(str(last_error) if last_error else "生成失败")


# --------------------------------------------------------------- 3D (Meshy)
def meshy_image_to_3d(image: str, out_path: str = "", ai_model: str = "meshy-4",
                      target_polycount: int = 1000, timeout: float = 600,
                      poll: float = 5.0) -> dict:
    """Meshy image-to-3d：本地图自动转 data URI，远程 URL 直接传。

    `image` 可以是本地路径、http(s) 链接或 data:image/...。
    没有 MESHY_API_KEY 就直说，不乱发请求。
    """
    key = _env("MESHY_API_KEY")
    if not key:
        raise ImageGenError(
            "没有 MESHY_API_KEY。Meshy 是付费服务，key 在其控制台申请；"
            "本工具的 3D 路径可以接，但需要你自带 key。")

    if str(image).startswith(("http://", "https://", "data:")):
        image_url = image
    else:
        p = Path(image).expanduser().resolve()
        if not p.exists():
            raise ImageGenError(f"图片不存在: {p}")
        raw = p.read_bytes()
        if len(raw) > 6 * 1024 * 1024:
            raise ImageGenError(f"图片 {len(raw)//1024} KB 超过 Meshy 单图上限（6 MB），先压缩")
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        image_url = f"data:{mime};base64," + base64.b64encode(raw).decode()

    created = _post_json(
        "https://api.meshy.ai/openapi/v1/image-to-3d",
        {"image_url": image_url, "ai_model": ai_model, "topology": "quad",
         "target_polycount": int(target_polycount), "should_remesh": True,
         "should_texture": False},
        {"Authorization": f"Bearer {key}"}, 60)
    task_id = created.get("result")
    if not task_id:
        raise ImageGenError(f"Meshy 没给 task id: {json.dumps(created)[:300]}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll)
        got = json.loads(_get_bytes(
            f"https://api.meshy.ai/openapi/v1/image-to-3d/{task_id}", 30,
            {"Authorization": f"Bearer {key}"}).decode())
        status = (got.get("status") or "").upper()
        if status in ("SUCCEEDED", "SUCCESS"):
            urls = got.get("model_urls") or {}
            glb = urls.get("glb") or ""
            if not glb:
                raise ImageGenError("任务成功但没有 glb 链接")
            out = Path(out_path).expanduser().resolve() if out_path else \
                config.exports_dir() / f"meshy_{task_id}.glb"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_get_bytes(glb, 300))
            return {"task_id": task_id, "status": status, "output": str(out),
                    "bytes": out.stat().st_size,
                    "note": "这是三角网格；要进 Minecraft 请跑 convert_to_cubes 转成方块"}
        if status in ("FAILED", "CANCELED"):
            raise ImageGenError(f"Meshy 任务失败: {json.dumps(got)[:300]}")
    raise ImageGenError(f"Meshy 超时（{timeout}s），task {task_id} 仍在跑；稍后用同一个 key 查任务")
