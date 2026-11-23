"""标准方块贴图：程序化材质 + 完整资源包结构（blockstate / model / item model）。

`generate_standard_block_texture` 不依赖图像服务：本地
程序化像素生成：材质关键词 → 结构模板 → 确定性噪声。产出可直接进资源包。
`publish_standard_block_asset` 负责把 staging 落到项目目录。
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image

from mc_craft_mcp import config
from . import state

MATERIALS = {
    "stone": {"label": "石头", "base": (128, 128, 132), "var": 18, "pattern": "noise"},
    "dirt": {"label": "泥土", "base": (122, 88, 62), "var": 22, "pattern": "noise"},
    "grass": {"label": "草", "base": (96, 148, 72), "var": 26, "pattern": "specks"},
    "wood": {"label": "木头", "base": (156, 120, 74), "var": 14, "pattern": "grain"},
    "plank": {"label": "木板", "base": (176, 140, 92), "var": 12, "pattern": "planks"},
    "metal": {"label": "金属", "base": (168, 174, 182), "var": 10, "pattern": "brushed"},
    "glass": {"label": "玻璃", "base": (198, 226, 232), "var": 6, "pattern": "glass"},
    "brick": {"label": "砖", "base": (150, 78, 62), "var": 12, "pattern": "brick"},
    "sand": {"label": "沙", "base": (216, 198, 148), "var": 16, "pattern": "noise"},
    "crystal": {"label": "晶体", "base": (128, 108, 198), "var": 30, "pattern": "facet"},
    "wool": {"label": "羊毛", "base": (206, 206, 210), "var": 8, "pattern": "weave"},
    "obsidian": {"label": "黑曜石", "base": (42, 34, 58), "var": 20, "pattern": "facet"},
}

KEYWORDS = {
    "stone": ("stone", "rock", "石", "岩"),
    "dirt": ("dirt", "soil", "土", "泥"),
    "grass": ("grass", "moss", "草", "苔"),
    "wood": ("wood", "log", "bark", "木", "原木"),
    "plank": ("plank", "board", "板"),
    "metal": ("metal", "iron", "steel", "铜", "铁", "钢", "金属"),
    "glass": ("glass", "玻璃", "透明"),
    "brick": ("brick", "砖"),
    "sand": ("sand", "沙"),
    "crystal": ("crystal", "gem", "amethyst", "晶", "宝石"),
    "wool": ("wool", "cloth", "fabric", "羊毛", "布"),
    "obsidian": ("obsidian", "黑曜"),
}


class BlockTexError(RuntimeError):
    pass


_WORD_INDEX = sorted(
    ((w, key) for key, words in KEYWORDS.items() for w in words),
    key=lambda kv: -len(kv[0]),
)


def _pick_material(text: str) -> str:
    """最长匹配优先："红宝石"里的"石"不能把 crystal 抢成 stone。"""
    low = (text or "").lower()
    for word, key in _WORD_INDEX:
        if word in low:
            return key
    return "stone"


def _clamp(v):
    return max(0, min(255, int(v)))


def _draw(material: str, size: int, seed: int, palette: list | None, stateful: bool) -> Image.Image:
    conf = MATERIALS.get(material, MATERIALS["stone"])
    base = conf["base"]
    if palette:
        try:
            h = palette[0].lstrip("#")
            base = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    var = conf["var"]
    pattern = conf["pattern"]
    rnd = random.Random(seed)
    img = Image.new("RGBA", (size, size), base + (255,))
    px = img.load()

    def shade(c, k):
        return tuple(_clamp(v * k) for v in c) + (255,)

    for y in range(size):
        for x in range(size):
            n = rnd.uniform(-var, var)
            c = tuple(_clamp(v + n) for v in base)
            if pattern == "grain":
                if x % max(2, size // 8) == 0:
                    c = shade(base, 0.82)
                elif (x + seed) % 7 == 0 and rnd.random() < 0.3:
                    c = shade(base, 1.08)
            elif pattern == "planks":
                band = y // max(2, size // 4)
                if y % max(2, size // 4) == 0:
                    c = shade(base, 0.72)
                elif (x + band * 5) % (size // 2 or 4) == 0:
                    c = shade(base, 0.86)
            elif pattern == "brushed":
                k = 0.9 + 0.2 * math.sin((x * math.pi * 2) / size)
                c = shade(base, k)
                if (y + seed) % (size // 2 or 4) == 0:
                    c = shade(base, 1.12)
            elif pattern == "brick":
                bh = max(2, size // 4)
                row = y // bh
                offset = (row % 2) * (size // 4)
                if y % bh == 0 or (x + offset) % max(2, size // 2) == 0:
                    c = shade(base, 0.7)
            elif pattern == "glass":
                edge = x in (0, size - 1) or y in (0, size - 1)
                if edge:
                    c = shade(base, 0.9)
                else:
                    alpha = 60 if not stateful else 110
                    px[x, y] = shade(base, 1.0)[:3] + (alpha,)
                    continue
            elif pattern == "facet":
                if (x * 3 + y * 5 + seed) % 17 == 0:
                    c = shade(base, 1.25)
                elif (x * 2 - y + seed) % 23 == 0:
                    c = shade(base, 0.7)
            elif pattern == "weave":
                if (x // 2 + y // 2) % 2 == 0:
                    c = shade(base, 1.04)
                if x % 2 == 0 or y % 2 == 0:
                    c = shade(base, 0.97)
            elif pattern == "specks":
                if rnd.random() < 0.08:
                    c = shade(base, 1.22)
                elif rnd.random() < 0.05:
                    c = shade(base, 0.78)
            px[x, y] = c
    return img


def generate_block_texture(
    project_dir: str,
    namespace: str,
    block_id: str,
    material_prompt: str,
    resolution: int = 16,
    face_layout: str = "all",
    palette: list | None = None,
    stateful_emissive_candidate: bool = False,
    canonical_state: str = "",
    overwrite: bool = False,
    dest_path: str = "",
) -> dict:
    if not block_id:
        raise BlockTexError("block_id 必填（小写字母、数字、下划线）")
    if not block_id.replace("_", "").isalnum() or block_id.lower() != block_id:
        raise BlockTexError(f"block_id 不合法: {block_id}（只允许小写字母/数字/下划线）")
    size = int(resolution) if int(resolution) in (16, 32, 64, 128) else 16

    material = _pick_material(material_prompt + " " + block_id)
    root = Path(project_dir).expanduser().resolve() if project_dir else config.projects_dir() / "blockpack"
    ns = namespace or "mcagent"
    seed = abs(hash((block_id, material))) % (2 ** 31)

    tex_dir = root / "assets" / ns / "textures" / "block"
    tex_dir.mkdir(parents=True, exist_ok=True)

    faces = ["all"] if face_layout == "all" else ["top", "side", "bottom"]
    written = []
    for face in faces:
        key_seed = seed + (0 if face == "all" else sum(ord(c) for c in face))
        img = _draw(material, size, key_seed, palette, stateful_emissive_candidate)
        name = block_id if face in ("all", "side") else f"{block_id}_{face}"
        path = tex_dir / f"{name}.png"
        if path.exists() and not overwrite:
            raise BlockTexError(f"已存在且未允许覆盖: {path}")
        img.save(path)
        written.append(str(path))

    # 方块状态 + 模型 + 物品模型
    model_ref = f"{ns}:block/{block_id}"
    blockstates = root / "assets" / ns / "blockstates"
    models_b = root / "assets" / ns / "models" / "block"
    models_i = root / "assets" / ns / "models" / "item"
    for d in (blockstates, models_b, models_i):
        d.mkdir(parents=True, exist_ok=True)

    (blockstates / f"{block_id}.json").write_text(json.dumps(
        {"variants": {"": {"model": model_ref}}}, indent=2), "utf-8")

    textures = {"particle": f"{ns}:block/{block_id}"}
    if "all" in faces:
        textures["all"] = f"{ns}:block/{block_id}"
    else:
        textures.update({
            "top": f"{ns}:block/{block_id}_top",
            "side": f"{ns}:block/{block_id}",
            "bottom": f"{ns}:block/{block_id}_bottom",
        })
    (models_b / f"{block_id}.json").write_text(json.dumps(
        {"parent": "minecraft:block/cube_all" if "all" in faces else "minecraft:block/cube_bottom_top",
         "textures": textures}, indent=2), "utf-8")
    (models_i / f"{block_id}.json").write_text(json.dumps(
        {"parent": model_ref}, indent=2), "utf-8")

    staging = {
        "kind": "standard_block",
        "material": material,
        "material_label": MATERIALS[material]["label"],
        "block_id": block_id,
        "namespace": ns,
        "project_dir": str(root),
        "resolution": size,
        "faces": faces,
        "textures": written,
        "palette_source": palette or [],
        "stateful_emissive_candidate": bool(stateful_emissive_candidate),
        "canonical_state": canonical_state,
        "created": state.now(),
    }
    staged = config.exports_dir() / f"block_{block_id}.staging.json"
    staged.write_text(json.dumps(staging, ensure_ascii=False, indent=1), "utf-8")
    staging["staging_metadata_path"] = str(staged)

    report = palette_report(str(Path(written[0]))) if written else {}
    staging["palette_report"] = report
    return staging


def palette_report(path: str, top: int = 8) -> dict:
    p = Path(path)
    if not p.exists():
        raise BlockTexError(f"图片不存在: {p}")
    img = Image.open(p).convert("RGBA")
    colors = img.getcolors(maxcolors=1 << 24) or []
    colors.sort(reverse=True)
    total = sum(c for c, _ in colors) or 1
    return {
        "size": list(img.size),
        "unique_colors": len(colors),
        "dominant": [
            {"hex": "#%02x%02x%02x" % c[:3], "share": round(n / total, 3)}
            for n, c in colors[:top]
        ],
    }


def publish_block_asset(staging_metadata: dict | str, project_dir: str = "") -> dict:
    if isinstance(staging_metadata, str):
        p = Path(staging_metadata)
        if p.exists():
            staging_metadata = json.loads(p.read_text("utf-8"))
        else:
            raise BlockTexError("staging_metadata 既不是对象也不是存在的文件")
    if not isinstance(staging_metadata, dict) or staging_metadata.get("kind") != "standard_block":
        raise BlockTexError("staging_metadata 不是本工具产出的标准方块记录")
    raw_root = project_dir or staging_metadata.get("project_dir") or ""
    if not raw_root:
        raise BlockTexError("没有目标项目目录：传 project_dir，或让 staging 记录带上它")
    root = Path(raw_root).expanduser().resolve()
    if not root.exists():
        raise BlockTexError(f"目标项目目录不存在: {root}")
    files = []
    for tex in staging_metadata.get("textures") or []:
        files.append(Path(tex).name)
    required = [
        root / "assets" / staging_metadata["namespace"] / "blockstates" / f"{staging_metadata['block_id']}.json",
        root / "assets" / staging_metadata["namespace"] / "models" / "block" / f"{staging_metadata['block_id']}.json",
        root / "assets" / staging_metadata["namespace"] / "models" / "item" / f"{staging_metadata['block_id']}.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    return {
        "published": not missing,
        "project_dir": str(root),
        "textures": files,
        "missing": missing,
        "note": "缺文件说明 staging 与项目目录不匹配，重新跑 generate_standard_block_texture 并指定同一 project_dir",
    }
