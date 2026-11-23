"""3D 资产管线：概念 → 立方体模型 → 贴图 → 动画 → 渲染 → 导出。

没有可用的 image-to-3d / retexture 服务时，本模块走确定性几何：
概念是一组可读的参数契约，模型是参数展开出来的 cube 树，贴图是调色板程序化绘制。
输出格式与 Blockbench 4.x 兼容，能被 Blockbench / GeckoLib / 资源包直接吃。

边界：不接受三角网格输入（`.glb` 里带 mesh 的文件只读包围盒与节点名），
`convert_to_cubes` 因此只对 cube 模型做归一化，不做真实网格拟合。
"""

from __future__ import annotations

import base64
import io
import json
import math
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from mc_craft_mcp import config
from . import state

ISO = math.radians(30)
COS, SIN = math.cos(ISO), math.sin(ISO)


class AssetError(RuntimeError):
    pass


# --------------------------------------------------------------- math / render
def _rot(point, origin, degrees):
    x, y, z = (point[i] - origin[i] for i in range(3))
    rx, ry, rz = (math.radians(d) for d in degrees)
    if rx:
        y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    if ry:
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    if rz:
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x + origin[0], y + origin[1], z + origin[2])


def _project(p):
    x, y, z = p
    return ((x - z) * COS, (x + z) * SIN - y)


FACES = {
    "up": ((0, 1, 0), 1.00),
    "down": ((0, -1, 0), 0.55),
    "north": ((0, 0, -1), 0.82),
    "south": ((0, 0, 1), 0.70),
    "east": ((1, 0, 0), 0.90),
    "west": ((-1, 0, 0), 0.76),
}

CORNERS = {
    "up": (4, 5, 6, 7),
    "down": (0, 1, 2, 3),
    "north": (0, 1, 5, 4),
    "south": (3, 2, 6, 7),
    "east": (1, 2, 6, 5),
    "west": (0, 3, 7, 4),
}


def _texture_image(model: dict):
    tex = (model.get("textures") or [{}])[0]
    src = tex.get("source") or ""
    if isinstance(src, str) and src.startswith("data:image"):
        try:
            raw = base64.b64decode(src.split(",", 1)[1])
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            return None
    return None


def _face_color(img, uv, shade, fallback=(150, 150, 150, 255)):
    if img is None or not uv:
        return tuple(int(c * shade) for c in fallback[:3]) + (255,)
    try:
        x1, y1, x2, y2 = [int(v) for v in uv]
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        box = img.crop((x1, y1, max(x2, x1 + 1), max(y2, y1 + 1)))
        px = list(box.resize((1, 1), Image.BOX).getdata())[0]
        return tuple(min(255, int(c * shade)) for c in px[:3]) + (px[3] if len(px) > 3 else 255,)
    except Exception:
        return tuple(int(c * shade) for c in fallback[:3]) + (255,)


def render_model(model: dict, out_path: str, size: int = 640, margin: int = 40) -> str:
    """等距投影 + 画家算法，纯 PIL。够看清造型，不当成品美术。"""
    elements = model.get("elements") or []
    if not elements:
        raise AssetError("模型没有 element，无法渲染")
    tex = _texture_image(model)

    polys = []
    for el in elements:
        frm, to = el.get("from"), el.get("to")
        origin = el.get("origin") or [0, 0, 0]
        rot = el.get("rotation") or [0, 0, 0]
        x1, y1, z1 = frm
        x2, y2, z2 = to
        pts = [
            (x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2),
            (x1, y2, z1), (x2, y2, z1), (x2, y2, z2), (x1, y2, z2),
        ]
        pts = [_rot(p, origin, rot) for p in pts]
        center = (sum(p[0] for p in pts) / 8, sum(p[1] for p in pts) / 8, sum(p[2] for p in pts) / 8)
        faces = el.get("faces") or {}
        for name, (normal, shade) in FACES.items():
            idx = CORNERS[name]
            quad = [pts[i] for i in idx]
            # 背面剔除：旋转后的面法线朝不朝向相机（视线方向 1,1,1）
            n = _rot([normal[0] + center[0], normal[1] + center[1], normal[2] + center[2]], center, rot)
            view = (n[0] - center[0], n[1] - center[1], n[2] - center[2])
            if view[0] + view[1] + view[2] <= 0:
                continue
            uv = (faces.get(name) or {}).get("uv")
            color = _face_color(tex, uv, shade)
            fx = sum(p[0] for p in quad) / 4
            fy = sum(p[1] for p in quad) / 4
            fz = sum(p[2] for p in quad) / 4
            polys.append((fx + fy + fz, [_project(p) for p in quad], color))

    polys.sort(key=lambda t: t[0])
    flat = [c for _, poly, _ in polys for c in poly]
    if not flat:
        raise AssetError("所有面都被剔除，检查 from/to 是否合法")
    minx = min(p[0] for p in flat); maxx = max(p[0] for p in flat)
    miny = min(p[1] for p in flat); maxy = max(p[1] for p in flat)
    span = max(maxx - minx, maxy - miny, 0.001)
    scale = (size - margin * 2) / span

    img = Image.new("RGBA", (size, size), (246, 246, 248, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    for _, poly, color in polys:
        pts = [((x - minx) * scale + margin, (y - miny) * scale + margin) for x, y in poly]
        draw.polygon(pts, fill=color, outline=(30, 30, 34, 60))

    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


# --------------------------------------------------------------- concepts
STYLES = [
    {"key": "chunky", "label": "敦实方正", "girth": 1.18, "leg": 0.52, "head": 0.46,
     "palette": ["#8a8f98", "#c9ced6", "#5b6169", "#e8e2d4"], "note": "低模块面，转角不留斜切，适合方块怪物"},
    {"key": "slim", "label": "修长轻巧", "girth": 0.92, "leg": 0.60, "head": 0.40,
     "palette": ["#6f7f8f", "#a9bccd", "#3f4a55", "#dfe7ee"], "note": "四肢细长、躯干窄，适合人形角色与工具"},
    {"key": "round", "label": "圆润可爱", "girth": 1.10, "leg": 0.45, "head": 0.52,
     "palette": ["#c98d6b", "#f0c9a8", "#8a5a3f", "#fff3e2"], "note": "大头短腿，立方体堆出圆感，适合宠物与吉祥物"},
    {"key": "mech", "label": "机械硬边", "girth": 1.05, "leg": 0.55, "head": 0.38,
     "palette": ["#4a4f57", "#8d949e", "#2a2d33", "#c1c7cf"], "note": "分层装甲板、外露关节，适合机械与载具"},
]


def concept_specs(prompt: str, kind: str = "model") -> list[dict]:
    """4 个可点的概念方案：给几何契约 + 缩略图，不依赖图像服务。"""
    out = []
    for style in STYLES:
        cid = state.new_id("concept")
        spec = {
            "concept_id": cid,
            "style": style["key"],
            "style_label": style["label"],
            "prompt": prompt,
            "kind": kind,
            "girth": style["girth"],
            "leg_ratio": style["leg"],
            "head_ratio": style["head"],
            "palette": style["palette"],
            "notes": style["note"],
            "created": state.now(),
        }
        model = model_from_concept(spec, name=f"concept_{style['key']}")
        thumb = config.exports_dir() / f"{cid}.png"
        try:
            render_model(model, str(thumb), size=320, margin=24)
            spec["thumbnail"] = str(thumb)
        except Exception as exc:  # noqa: BLE001
            spec["thumbnail_error"] = str(exc)
        out.append(spec)
    state.add_concepts(out)
    return out


# --------------------------------------------------------------- model build
def _cube(name, frm, to, uv=None, origin=None, rotation=None, inflate=0.0):
    return {
        "name": name,
        "from": [round(v, 4) for v in frm],
        "to": [round(v, 4) for v in to],
        "origin": origin or [0, 0, 0],
        "rotation": rotation or [0, 0, 0],
        "uv": uv or {},
        "inflate": inflate,
    }


def model_from_concept(concept: dict, name: str = "") -> dict:
    """把概念参数展开成 cube 树。这是几何契约的落地，不是美术发挥。"""
    g = float(concept.get("girth", 1.0))
    legr = float(concept.get("leg_ratio", 0.5))
    headr = float(concept.get("head_ratio", 0.45))
    kind = (concept.get("kind") or "model").lower()

    groups: list[dict] = []
    if kind in ("item", "icon", "prop"):
        groups.append({"name": "body", "origin": [0, 0, 0], "cubes": [
            _cube("core", [-4 * g, 0, -4 * g], [4 * g, 8 * g, 4 * g]),
            _cube("detail", [-2 * g, 8 * g, -2 * g], [2 * g, 10 * g, 2 * g]),
        ]})
        height = 10 * g
    elif kind in ("quadruped", "pet", "mount"):
        body_h = 6 * g
        leg_h = 8 * legr
        groups.append({"name": "body", "origin": [0, leg_h, 0], "cubes": [
            _cube("torso", [-5 * g, leg_h, -8 * g], [5 * g, leg_h + body_h, 8 * g]),
        ]})
        groups.append({"name": "head", "origin": [0, leg_h + body_h, -8 * g], "cubes": [
            _cube("skull", [-3.5 * g, leg_h + body_h - 1, -8 * g - 7 * headr * 10],
                  [3.5 * g, leg_h + body_h + 5 * headr * 10, -8 * g]),
        ]})
        for side, sx in (("left", 1), ("right", -1)):
            for pos, sz in (("front", -1), ("back", 1)):
                groups.append({
                    "name": f"leg_{pos}_{side}",
                    "origin": [sx * 3.5 * g, leg_h, sz * 5 * g],
                    "cubes": [_cube(f"{pos}_{side}", [sx * 3.5 * g - 1.5, 0, sz * 5 * g - 1.5],
                                    [sx * 3.5 * g + 1.5, leg_h, sz * 5 * g + 1.5])],
                })
        groups.append({"name": "tail", "origin": [0, leg_h + body_h * 0.6, 8 * g], "cubes": [
            _cube("tail", [-1.2, leg_h + body_h * 0.6, 8 * g], [1.2, leg_h + body_h * 0.6 + 2, 8 * g + 6]),
        ]})
        height = leg_h + body_h + 5 * headr * 10
    else:  # humanoid 默认
        leg_h = 12 * legr
        torso_h = 12 * g * 0.7
        head_s = 8 * headr * 2
        groups.append({"name": "body", "origin": [0, leg_h + torso_h, 0], "cubes": [
            _cube("torso", [-4 * g, leg_h, -2 * g], [4 * g, leg_h + torso_h, 2 * g]),
        ]})
        groups.append({"name": "head", "origin": [0, leg_h + torso_h, 0], "cubes": [
            _cube("skull", [-head_s / 2, leg_h + torso_h, -head_s / 2],
                  [head_s / 2, leg_h + torso_h + head_s, head_s / 2]),
        ]})
        for side, sx in (("left", 1), ("right", -1)):
            groups.append({
                "name": f"arm_{side}",
                "origin": [sx * 4 * g, leg_h + torso_h, 0],
                "cubes": [_cube(f"arm_{side}", [sx * 4 * g - 2, leg_h + torso_h - 10 * g, -2],
                                [sx * 4 * g + 2, leg_h + torso_h, 2])],
            })
            groups.append({
                "name": f"leg_{side}",
                "origin": [sx * 2, leg_h, 0],
                "cubes": [_cube(f"leg_{side}", [sx * 2 - 2, 0, -2], [sx * 2 + 2, leg_h, 2])],
            })
        height = leg_h + torso_h + head_s

    spec = {
        "name": name or concept.get("style", "model"),
        "resolution": 16,
        "groups": groups,
        "model_format": "java_block",
    }
    from mc_craft_mcp.model import build_model
    model = build_model(spec)
    model["_mcagent"] = {
        "concept_id": concept.get("concept_id"),
        "style": concept.get("style"),
        "palette": concept.get("palette"),
        "height": round(height, 2),
        "prompt": concept.get("prompt"),
    }
    return model


# --------------------------------------------------------------- texture
def _palette_rgb(hexes):
    out = []
    for h in hexes:
        h = h.lstrip("#")
        out.append(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    return out


def paint_model(model: dict, style_prompt: str = "", resolution: int = 16, palette: list | None = None) -> dict:
    """程序化像素贴图：按语义部分（躯干/头/四肢）分配色阶，加确定性噪点。"""
    cols = _palette_rgb(palette or ["#8a8f98", "#c9ced6", "#5b6169", "#e8e2d4"])
    size = max(8, min(128, int(resolution)))
    img = Image.new("RGBA", (size * 4, size), (0, 0, 0, 0))
    px = img.load()
    seed = sum(ord(c) for c in (style_prompt or "default"))
    for band, base in enumerate(cols):
        for y in range(size):
            for x in range(size):
                n = ((x * 7 + y * 13 + seed + band * 29) % 11) / 11.0
                k = 0.82 + n * 0.36
                c = tuple(min(255, int(v * k)) for v in base)
                px[band * size + x, y] = c + (255,)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    model = json.loads(json.dumps(model))
    model["textures"] = [{
        "path": "", "name": f"{model.get('name','model')}.png", "folder": "",
        "namespace": "", "id": "0", "particle": False, "render_mode": "default",
        "visible": True, "mode": "bitmap", "saved": False,
        "uuid": "tex-" + str(seed), "source": data,
    }]
    # 面 UV 按部分分配到不同色带
    band_of = {"body": 0, "head": 1, "arm": 2, "leg": 3, "tail": 2,
               "torso": 0, "skull": 1, "core": 0, "detail": 1}
    for grp in model.get("outliner") or []:
        gname = (grp.get("name") or "").lower()
        band = 0
        for key, val in band_of.items():
            if key in gname:
                band = val
                break
        for idx in grp.get("children") or []:
            if not isinstance(idx, int) or idx >= len(model["elements"]):
                continue
            el = model["elements"][idx]
            for face, fdata in (el.get("faces") or {}).items():
                fdata["texture"] = 0
                fdata["uv"] = [band * size, 0, (band + 1) * size, size]
    return model


# --------------------------------------------------------------- bones / anim
def bones_of(model: dict) -> list[dict]:
    rows = []
    for i, grp in enumerate(model.get("outliner") or []):
        rows.append({
            "name": grp.get("name") or f"group{i}",
            "parent": grp.get("parent") or None,
            "pivot": grp.get("origin") or [0, 0, 0],
            "cubes": len([c for c in (grp.get("children") or []) if isinstance(c, int)]),
        })
    return rows


def apply_animation(model: dict, name: str, length: float, loop: str, keyframes: list[dict]) -> dict:
    if not keyframes:
        raise AssetError("bones 为空：至少给一组关键帧，否则动画是空的")
    bone_names = {b["name"] for b in bones_of(model)}
    unknown = [k.get("bone") for k in keyframes if k.get("bone") not in bone_names]
    if unknown:
        raise AssetError(f"未知骨骼 {unknown}；先调 list_model_bones，可用: {sorted(bone_names)}")

    animators = {}
    for k in keyframes:
        bone = k["bone"]
        anim = animators.setdefault(bone, {"name": bone, "type": "bone", "keyframes": []})
        kf = {"channel": k.get("channel", "rotation"), "time": float(k.get("time", 0))}
        if "vector" in k:
            vec = [float(v) for v in k["vector"]]
            kf["data_points"] = [{"x": vec[0], "y": vec[1], "z": vec[2]}]
        elif "value" in k:
            kf["data_points"] = [{"x": float(k["value"]), "y": float(k["value"]), "z": float(k["value"])}]
        else:
            raise AssetError(f"关键帧缺 vector/value: {k}")
        anim["keyframes"].append(kf)

    # 整模竖直位移钳制：下去会穿地，上去像漂浮
    for bone, anim in animators.items():
        for kf in anim["keyframes"]:
            if kf["channel"] == "position":
                for dp in kf["data_points"]:
                    dp["y"] = max(0.0, min(dp["y"], 0.0))

    model = json.loads(json.dumps(model))
    model.setdefault("animations", [])
    model["animations"] = [a for a in model["animations"] if a.get("name") != name]
    model["animations"].append({
        "name": name,
        "loop": loop if loop in ("once", "hold", "loop") else "loop",
        "override": False,
        "length": float(length),
        "snapping": 24,
        "animators": animators,
        "uuid": state.new_id("anim"),
    })
    return model


# --------------------------------------------------------------- io
def read_model(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise AssetError(f"文件不存在: {p}")
    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AssetError(f"不是合法 .bbmodel: {exc}") from exc
    if "elements" not in data:
        raise AssetError("缺少 elements，不是 Blockbench 模型")
    return data


def write_model(model: dict, path: str = "", name: str = "") -> dict:
    from mc_craft_mcp.model import validate_model

    out = Path(path).expanduser().resolve() if path else \
        config.exports_dir() / f"{(name or model.get('name') or 'model')}.bbmodel"
    out.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in model.items() if not k.startswith("_")}
    out.write_text(json.dumps(clean, ensure_ascii=False, indent=2), "utf-8")
    report = validate_model(str(out))
    return {"output": str(out), "bytes": out.stat().st_size, "validation": report}


def export_glb(model: dict, out_path: str) -> str:
    """最小 glTF 2.0 二进制：cube 顶点 + 索引 + 顶点色，不写贴图。"""
    verts, colors, indices = [], [], []
    for el in model.get("elements") or []:
        x1, y1, z1 = el["from"]
        x2, y2, z2 = el["to"]
        base = len(verts) // 3
        corners = [
            (x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2),
            (x1, y2, z1), (x2, y2, z1), (x2, y2, z2), (x1, y2, z2),
        ]
        for c in corners:
            verts.extend(c)
            colors.extend([0.62, 0.66, 0.72, 1.0])
        for idx in CORNERS.values():
            indices.extend([base + idx[0], base + idx[1], base + idx[2],
                            base + idx[0], base + idx[2], base + idx[3]])

    import struct
    vbytes = struct.pack("<%df" % len(verts), *verts)
    cbytes = struct.pack("<%df" % len(colors), *colors)
    ibytes = struct.pack("<%dI" % len(indices), *indices)
    pad = lambda b, n=4: b + b"\x00" * ((n - len(b) % n) % n)
    vbytes, cbytes, ibytes = pad(vbytes), pad(cbytes), pad(ibytes)
    bin_blob = vbytes + cbytes + ibytes

    gltf = {
        "asset": {"version": "2.0", "generator": "mc-agent"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": model.get("name", "model")}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "COLOR_0": 1},
            "indices": 2, "mode": 4,
        }]}],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vbytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(vbytes), "byteLength": len(cbytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(vbytes) + len(cbytes), "byteLength": len(ibytes), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(verts) // 3, "type": "VEC3",
             "min": [min(verts[i::3]) for i in range(3)], "max": [max(verts[i::3]) for i in range(3)]},
            {"bufferView": 1, "componentType": 5126, "count": len(colors) // 4, "type": "VEC4"},
            {"bufferView": 2, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
    }
    jbytes = pad(json.dumps(gltf, separators=(",", ":")).encode())
    total = 12 + 8 + len(jbytes) + 8 + len(bin_blob)
    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, total))
        f.write(struct.pack("<I", len(jbytes)) + b"JSON" + jbytes)
        f.write(struct.pack("<I", len(bin_blob)) + b"BIN\x00" + bin_blob)
    return str(out)


def export_resourcepack(model: dict, out_zip: str, namespace: str, entity_base: str, texture: Image.Image | None) -> dict:
    """Java 资源包：模型 + 贴图 + 物品模型 + 可选实体绑定。"""
    ns = namespace or "mcagent"
    name = (model.get("name") or "model").replace(" ", "_")
    pack = {
        "pack": {
            "pack_format": 34,
            "description": f"mc-agent export: {name}",
        }
    }
    files: dict[str, bytes] = {}
    files["pack.mcmeta"] = json.dumps(pack, ensure_ascii=False, indent=2).encode()

    clean = {k: v for k, v in model.items() if not k.startswith("_")}
    files[f"assets/{ns}/models/item/{name}.json"] = json.dumps(clean, ensure_ascii=False).encode()

    if texture is not None:
        buf = io.BytesIO()
        texture.save(buf, format="PNG")
        files[f"assets/{ns}/textures/item/{name}.png"] = buf.getvalue()

    if entity_base:
        files[f"assets/{ns}/models/entity/{name}.json"] = json.dumps(clean, ensure_ascii=False).encode()

    out = Path(out_zip).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr(path, data)
    return {"output": str(out), "files": sorted(files), "bytes": out.stat().st_size}


def import_glb_summary(path: str) -> dict:
    """只读 glb 的 JSON 块：节点名、网格数、包围盒。不做三角网格转立方体。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise AssetError(f"文件不存在: {p}")
    raw = p.read_bytes()
    if raw[:4] != b"glTF":
        raise AssetError("不是 GLB（magic 不匹配）")
    length = int.from_bytes(raw[12:16], "little")
    import struct
    jlen = struct.unpack("<I", raw[12:16])[0]
    gltf = json.loads(raw[20:20 + jlen])
    return {
        "path": str(p),
        "nodes": [n.get("name") for n in gltf.get("nodes", [])],
        "meshes": len(gltf.get("meshes", [])),
        "animations": [a.get("name") for a in gltf.get("animations", [])],
        "note": "只读了结构；三角网格转立方体不在本地能力内",
    }
