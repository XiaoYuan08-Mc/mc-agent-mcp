"""自发光：mask 提取 → 点亮态 overlay。

这两步都落到同一个 staging manifest 上：mask 决定哪些像素发光，
overlay 决定发光时那块像素变成什么颜色。这里保持同样的因果顺序，
只做像素阈值与颜色映射，不重画贴图。
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from mc_craft_mcp import config
from . import state


class EmissiveError(RuntimeError):
    pass


def _load(p: str) -> Image.Image:
    path = Path(p)
    if not path.exists():
        raise EmissiveError(f"图片不存在: {path}")
    return Image.open(path).convert("RGBA")


def build_mask(
    staging_metadata: dict | str,
    emissive_mode: str = "threshold",
    activation: str = "always",
    world_light_level: int = 0,
    regions: list | None = None,
    intensity_mode: str = "binary",
    threshold: int = 0,
) -> dict:
    if isinstance(staging_metadata, str):
        p = Path(staging_metadata)
        if not p.exists():
            raise EmissiveError(f"staging 文件不存在: {p}")
        staging_metadata = json.loads(p.read_text("utf-8"))
    textures = staging_metadata.get("textures") or []
    if not textures:
        raise EmissiveError("staging 里没有 textures，先跑 generate_standard_block_texture")

    out_dir = Path(staging_metadata.get("project_dir") or config.exports_dir())
    ns = staging_metadata.get("namespace", "mcagent")
    block_id = staging_metadata.get("block_id", "block")
    tex_dir = out_dir / "assets" / ns / "textures" / "block"
    glow_dir = out_dir / "assets" / ns / "textures" / "block" / "glow"
    glow_dir.mkdir(parents=True, exist_ok=True)

    masks = []
    for tex in textures:
        img = _load(tex)
        w, h = img.size
        src = img.load()
        mask = Image.new("L", (w, h), 0)
        mpx = mask.load()
        # threshold<=0 表示自动：取该贴图亮度的 90 分位，深色材质也能选出高光
        local_threshold = int(threshold)
        if local_threshold <= 0:
            lums = sorted(
                0.2126 * src[x, y][0] + 0.7152 * src[x, y][1] + 0.0722 * src[x, y][2]
                for y in range(h) for x in range(w) if src[x, y][3] > 0)
            local_threshold = int(lums[int(len(lums) * 0.9)]) if lums else 128

        for y in range(h):
            for x in range(w):
                r, g, b, a = src[x, y]
                if a == 0:
                    continue
                inside = True
                if regions:
                    inside = any(
                        int(rg.get("x", 0)) <= x < int(rg.get("x", 0)) + int(rg.get("w", w))
                        and int(rg.get("y", 0)) <= y < int(rg.get("y", 0)) + int(rg.get("h", h))
                        for rg in regions
                    )
                if not inside:
                    continue
                lum = int(0.2126 * r + 0.7152 * g + 0.0722 * b)
                if emissive_mode == "manual":
                    continue
                if lum >= local_threshold:
                    mpx[x, y] = 255 if intensity_mode == "binary" else min(255, int(lum * 1.25))
        name = Path(tex).stem
        mask_path = glow_dir / f"{name}_emissive.png"
        mask.save(mask_path)
        lit = sum(1 for v in mask.getdata() if v > 0)
        masks.append({
            "source": str(tex),
            "mask": str(mask_path),
            "lit_pixels": lit,
            "lit_ratio": round(lit / max(1, w * h), 4),
        })

    manifest = {
        "kind": "emissive_mask",
        "block_id": block_id,
        "namespace": ns,
        "project_dir": str(out_dir),
        "emissive_mode": emissive_mode,
        "activation": activation,
        "world_light_level": int(world_light_level),
        "intensity_mode": intensity_mode,
        "threshold": local_threshold,
        "regions": regions or [],
        "masks": masks,
        "created": state.now(),
    }
    mpath = config.exports_dir() / f"{block_id}_emissive_mask.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    manifest["mask_manifest_path"] = str(mpath)
    return manifest


def build_overlay(
    mask_manifest: dict | str,
    state_change: str = "",
    face_edits: list | None = None,
    glow_color: list | None = None,
    multiply: float = 1.35,
) -> dict:
    if isinstance(mask_manifest, str):
        p = Path(mask_manifest)
        if not p.exists():
            raise EmissiveError(f"mask manifest 不存在: {p}")
        mask_manifest = json.loads(p.read_text("utf-8"))
    if mask_manifest.get("kind") != "emissive_mask":
        raise EmissiveError("mask_manifest 不是本工具产出的 emissive 记录")

    color = glow_color or [255, 214, 140]
    edits = {e.get("face"): e for e in (face_edits or [])}
    outputs = []
    for rec in mask_manifest.get("masks") or []:
        src = _load(rec["source"])
        mask = _load(rec["mask"]).convert("L")
        w, h = src.size
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sp, mp, op = src.load(), mask.load(), out.load()
        for y in range(h):
            for x in range(w):
                if mp[x, y] == 0:
                    continue
                r, g, b, a = sp[x, y]
                k = multiply * (mp[x, y] / 255.0)
                nr = min(255, int((r * 0.45 + color[0] * 0.55) * k))
                ng = min(255, int((g * 0.45 + color[1] * 0.55) * k))
                nb = min(255, int((b * 0.45 + color[2] * 0.55) * k))
                op[x, y] = (nr, ng, nb, a)

        name = Path(rec["source"]).stem
        out_path = Path(rec["mask"]).parent / f"{name}_emissive_overlay.png"
        out.save(out_path)
        outputs.append({"source": rec["source"], "overlay": str(out_path), "state": state_change or "lit"})

    result = {
        "kind": "emissive_overlay",
        "block_id": mask_manifest.get("block_id"),
        "namespace": mask_manifest.get("namespace"),
        "project_dir": mask_manifest.get("project_dir"),
        "state_change": state_change,
        "glow_color": color,
        "outputs": outputs,
        "face_edits_applied": list(edits),
        "created": state.now(),
    }
    opath = config.exports_dir() / f"{mask_manifest.get('block_id','block')}_emissive_overlay.json"
    opath.write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    result["overlay_manifest_path"] = str(opath)
    return result
