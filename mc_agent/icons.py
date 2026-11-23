"""物品图标：模型 / 图片 → 32px 像素图标（可抠背景、可量化调色板）。"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from mc_craft_mcp import config
from . import assets, state


class IconError(RuntimeError):
    pass


def _content_box(img: Image.Image, tol: int = 12):
    rgb = img.convert("RGBA")
    w, h = rgb.size
    px = rgb.load()
    bg = px[0, 0]
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if abs(r - bg[0]) <= tol and abs(g - bg[1]) <= tol and abs(b - bg[2]) <= tol:
                continue
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
    if maxx < 0:
        return (0, 0, w, h)
    return (minx, miny, maxx + 1, maxy + 1)


def make_icon(
    source: str,
    out_path: str = "",
    size: int = 32,
    background_color: str = "",
    background_tolerance: int = 10,
    quantize: bool = True,
) -> dict:
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise IconError(f"源文件不存在: {src}")

    if src.suffix.lower() == ".bbmodel":
        model = assets.read_model(str(src))
        tmp = config.exports_dir() / f"{src.stem}_icon_src.png"
        assets.render_model(model, str(tmp), size=512, margin=16)
        img = Image.open(tmp).convert("RGBA")
        source_kind = "model_render"
    else:
        img = Image.open(src).convert("RGBA")
        source_kind = "image"

    if background_color:
        h = background_color.lstrip("#")
        target = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        tol = max(0, int(background_tolerance))
        px = img.load()
        for y in range(img.size[1]):
            for x in range(img.size[0]):
                r, g, b, a = px[x, y]
                if abs(r - target[0]) <= tol and abs(g - target[1]) <= tol and abs(b - target[2]) <= tol:
                    px[x, y] = (0, 0, 0, 0)

    box = _content_box(img, tol=max(4, background_tolerance))
    cropped = img.crop(box)
    side = max(cropped.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cropped, ((side - cropped.size[0]) // 2, (side - cropped.size[1]) // 2))
    icon = canvas.resize((size, size), Image.NEAREST)
    if quantize:
        icon = icon.quantize(colors=32, method=Image.FASTOCTREE).convert("RGBA")

    out = Path(out_path).expanduser().resolve() if out_path else \
        config.exports_dir() / f"{src.stem}_{size}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    icon.save(out)

    colors = icon.getcolors(maxcolors=1 << 20) or []
    return {
        "output": str(out),
        "source": str(src),
        "source_kind": source_kind,
        "size": [size, size],
        "content_box": list(box),
        "unique_colors": len(colors),
        "opaque_pixels": sum(n for n, c in colors if c[3] > 0),
    }


def render_inventory(model_path: str, out_path: str = "", size: int = 64) -> dict:
    model = assets.read_model(model_path)
    out = out_path or str(config.exports_dir() / f"{Path(model_path).stem}_inventory.png")
    path = assets.render_model(model, out, size=max(128, size), margin=12)
    img = Image.open(path)
    img = img.resize((size, size), Image.NEAREST)
    img.save(path)
    return {"output": path, "size": [size, size]}
