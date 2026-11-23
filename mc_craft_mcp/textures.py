"""Deterministic pixel post-processing: block textures, item icons, emissive masks.

These tools only do what is mechanically checkable (size, palette, alpha, masks,
seams). Aesthetic judgement stays with the model, which is why every result
reports raw numbers instead of a score.
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image

from . import config


class TextureError(RuntimeError):
    pass


def _load(path: str) -> Image.Image:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise TextureError(f"图片不存在: {p}")
    return Image.open(p).convert("RGBA")


def _square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _seam_score(img: Image.Image) -> dict:
    import math
    w, h = img.size
    px = img.load()
    lint = 0.0
    for y in range(h):
        for c in range(3):
            lint += abs(px[0, y][c] - px[w - 1, y][c]) / 255.0
    ltot = 0.0
    for x in range(w):
        for c in range(3):
            ltot += abs(px[x, 0][c] - px[x, h - 1][c]) / 255.0
    perim = h * 3
    return {
        "left_right_diff": round(lint / perim, 4),
        "top_bottom_diff": round(ltot / perim, 4),
        "tileable_hint": (lint + ltot) / (perim * 2) < 0.02,
    }


def block_texture(
    source: str,
    output: str = "",
    size: int = 16,
    colors: int = 16,
    alpha_threshold: int = 128,
    quantize: bool = True,
) -> dict:
    if size < 8 or size > 256:
        raise TextureError("size 必须在 8..256（方块纹理通常 16）")
    img = _load(source)
    img = _square(img).resize((size, size), Image.Resampling.NEAREST)

    alpha = img.getchannel("A").point(lambda a: 255 if a >= alpha_threshold else 0)
    rgb = img.convert("RGB")
    if quantize:
        pal = rgb.quantize(colors=max(2, min(colors, 256)), method=Image.Quantize.MEDIANCUT,
                           dither=Image.Dither.NONE).convert("RGB")
        distinct = len({p for p in pal.getdata()})
    else:
        pal = rgb
        distinct = len({p for p in rgb.getdata()})
    result = pal.convert("RGBA")
    result.putalpha(alpha)

    out = Path(output).expanduser().resolve() if output \
        else config.exports_dir() / (Path(source).stem + f"_{size}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out, "PNG")

    opaque = sum(1 for p in alpha.getdata() if p)
    return {
        "output": str(out),
        "size": [size, size],
        "colors_used": distinct,
        "opaque_pixels": opaque,
        "opaque_ratio": round(opaque / (size * size), 3),
        "seam": _seam_score(result),
        "note": "最近邻缩放 + 中位切分调色板；不做平滑、不做插值",
    }


def item_icon(
    source: str,
    output: str = "",
    size: int = 32,
    remove_background: bool = False,
    background_color: str = "",
    tolerance: int = 12,
) -> dict:
    if size < 8 or size > 512:
        raise TextureError("size 必须在 8..512（物品栏图标通常 16 或 32）")
    img = _square(_load(source)).resize((size, size), Image.Resampling.NEAREST)

    removed = 0
    if remove_background and background_color:
        try:
            bg = Image.new("RGBA", (1, 1), background_color).getpixel((0, 0))
        except Exception as exc:  # noqa: BLE001
            raise TextureError(f"background_color 解析失败: {exc}") from exc
        px = img.load()
        for y in range(size):
            for x in range(size):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                dist = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
                if dist <= tolerance:
                    px[x, y] = (r, g, b, 0)
                    removed += 1

    bbox = img.getbbox()
    out = Path(output).expanduser().resolve() if output \
        else config.exports_dir() / (Path(source).stem + f"_icon{size}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return {
        "output": str(out),
        "size": [size, size],
        "background_removed_pixels": removed,
        "content_bbox": list(bbox) if bbox else None,
        "palette": len({p for p in img.getdata() if p[3] > 0}),
    }


def emissive_mask(
    base: str,
    output_dir: str = "",
    threshold: int = 150,
    tint: str = "#ffffff",
    size: int | None = None,
) -> dict:
    img = _load(base)
    if size:
        img = _square(img).resize((size, size), Image.Resampling.NEAREST)
    if img.size[0] != img.size[1]:
        img = _square(img)
    w, h = img.size
    try:
        tint_rgb = Image.new("RGB", (1, 1), tint).getpixel((0, 0))
    except Exception as exc:  # noqa: BLE001
        raise TextureError(f"tint 解析失败: {exc}") from exc

    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    lit = img.copy()
    px_in, px_mask, px_lit = img.load(), mask.load(), lit.load()
    count = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px_in[x, y]
            if a == 0:
                continue
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if lum >= threshold:
                px_mask[x, y] = (255, 255, 255, 255)
                nr = int(min(255, r * tint_rgb[0] / 255 * 1.25))
                ng = int(min(255, g * tint_rgb[1] / 255 * 1.25))
                nb = int(min(255, b * tint_rgb[2] / 255 * 1.25))
                px_lit[x, y] = (nr, ng, nb, a)
                count += 1

    out_dir = Path(output_dir).expanduser().resolve() if output_dir else config.exports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(base).stem
    mask_path = out_dir / f"{stem}_emissive_mask.png"
    lit_path = out_dir / f"{stem}_lit.png"
    mask.save(mask_path, "PNG")
    lit.save(lit_path, "PNG")
    return {
        "mask": str(mask_path),
        "lit": str(lit_path),
        "size": [w, h],
        "emissive_pixels": count,
        "emissive_ratio": round(count / (w * h), 3),
        "threshold": threshold,
        "tint": tint,
    }


def palette_report(path: str, top: int = 8) -> dict:
    img = _load(path)
    colors: dict[tuple, int] = {}
    for r, g, b, a in img.getdata():
        if a == 0:
            continue
        colors[(r, g, b)] = colors.get((r, g, b), 0) + 1
    ranked = sorted(colors.items(), key=lambda kv: kv[1], reverse=True)[:top]
    detail = []
    for (r, g, b), n in ranked:
        hls = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        detail.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "pixels": n,
                       "hue": round(hls[0] * 360, 1)})
    return {"path": str(Path(path).resolve()), "size": list(img.size),
            "distinct_colors": len(colors), "top": detail}
