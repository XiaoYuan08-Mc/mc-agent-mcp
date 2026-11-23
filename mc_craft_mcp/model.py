"""Blockbench .bbmodel writing and structural validation.

The writer accepts a small, explicit cube-tree spec (no free-form guessing) and
emits a Blockbench 4.x model. Validation reports structural facts only: counts,
uv bounds, degenerate boxes, missing faces, dangling outliner references.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import config

FACES = ("north", "east", "south", "west", "up", "down")


class ModelError(RuntimeError):
    pass


def _vec3(value, field: str) -> list:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ModelError(f"{field} 必须是 [x, y, z] 三元数组")
    return [float(v) for v in value]


def _face(name: str, uv: list, texture: int | None) -> dict:
    return {"uv": uv, "texture": texture, "rotation": 0, "tint_color": -1}


def _element(cube: dict, resolution: int, texture_index: int | None) -> dict:
    frm = _vec3(cube.get("from"), "from")
    to = _vec3(cube.get("to"), "to")
    origin = _vec3(cube.get("origin", [0, 0, 0]), "origin")
    rotation = _vec3(cube.get("rotation", [0, 0, 0]), "rotation")
    if any(t - f <= 0 for f, t in zip(frm, to)):
        raise ModelError(f"cube {cube.get('name')} 的 from 必须严格小于 to")
    size = [t - f for f, t in zip(frm, to)]
    uv_spec = cube.get("uv") or {}
    faces = {}
    for face in FACES:
        uv = uv_spec.get(face) or [0, 0, 0, 0]
        if face in ("north", "south"):
            uv = uv_spec.get(face) or [0, 0, size[0], size[1]]
        elif face in ("east", "west"):
            uv = uv_spec.get(face) or [0, 0, size[2], size[1]]
        else:
            uv = uv_spec.get(face) or [0, 0, size[0], size[2]]
        faces[face] = _face(face, [float(u) for u in uv], texture_index)

    element = {
        "name": cube.get("name", "cube"),
        "box_uv": False,
        "rescale": False,
        "locked": False,
        "light_emission": int(cube.get("light_emission", 0)),
        "render_order": "default",
        "allow_mirror_modeling": True,
        "from": frm,
        "to": to,
        "autouv": 0,
        "color": 0,
        "origin": origin,
        "faces": faces,
        "type": "cube",
        "inflate": float(cube.get("inflate", 0)),
    }
    if any(abs(r) > 90 for r in rotation):
        raise ModelError(f"cube {cube.get('name')} 的 rotation 超出 ±90")
    element["rotation"] = rotation
    if cube.get("mirror_uv"):
        element["mirror_uv"] = True
    return element


def build_model(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ModelError("spec 必须是对象")
    resolution = spec.get("resolution", 16)
    if isinstance(resolution, (list, tuple)):
        width, height = int(resolution[0]), int(resolution[1])
    else:
        width = height = int(resolution)

    texture = spec.get("texture")
    textures = [texture] if texture else []

    elements: list[dict] = []
    outliner: list = []
    groups = spec.get("groups") or []
    if not groups and spec.get("cubes"):
        groups = [{"name": spec.get("name", "model"), "cubes": spec["cubes"]}]
    if not groups:
        raise ModelError("spec 里没有任何 groups/cubes")

    for group in groups:
        cubes = group.get("cubes") or []
        if not cubes:
            continue
        children: list[int] = []
        for cube in cubes:
            idx = len(elements)
            elements.append(_element(cube, width, 0 if texture else None))
            children.append(idx)
        outliner.append({
            "name": group.get("name", "group"),
            "origin": _vec3(group.get("origin", [0, 0, 0]), "group.origin"),
            "uuid": None,
            "export": True,
            "mirror_uv": False,
            "is_mesh": False,
            "needs_local_orientation": False,
            "children": children,
        })

    model = {
        "meta": {
            "format_version": "4.10",
            "model_format": spec.get("model_format", "java_block"),
            "box_uv": False,
        },
        "name": spec.get("name", "model"),
        "model_identifier": spec.get("model_identifier", spec.get("name", "model")),
        "variable_placeholders": "",
        "variable_placeholder_buttons": [],
        "resolution": {"width": width, "height": height},
        "elements": elements,
        "outliner": outliner,
        "textures": textures,
        "display": {},
    }
    return model


def write_model(spec: dict, output: str = "") -> dict:
    model = build_model(spec)
    out = Path(output).expanduser().resolve() if output \
        else config.exports_dir() / f"{model['name']}.bbmodel"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output": str(out),
        "cubes": len(model["elements"]),
        "groups": len(model["outliner"]),
        "resolution": model["resolution"],
        "has_texture": bool(model["textures"]),
        "bytes": out.stat().st_size,
    }


def validate_model(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ModelError(f"文件不存在: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ModelError(f"不是合法 JSON: {exc}") from exc

    issues: list[str] = []
    elements = data.get("elements") or []
    res = data.get("resolution") or {}
    rw, rh = int(res.get("width", 16)), int(res.get("height", 16))

    for i, el in enumerate(elements):
        frm, to = el.get("from"), el.get("to")
        if not frm or not to:
            issues.append(f"element[{i}] 缺少 from/to")
            continue
        for a, b in zip(frm, to):
            if any(math.isnan(v) for v in (a, b)):
                issues.append(f"element[{i}] 坐标含 NaN")
            if b <= a:
                issues.append(f"element[{i}] 尺寸非正: {frm} -> {to}")
        faces = el.get("faces") or {}
        if len(faces) != 6:
            issues.append(f"element[{i}] 面数 {len(faces)} != 6（不是完整立方体）")
        for name, face in faces.items():
            uv = face.get("uv") or [0, 0, 0, 0]
            if len(uv) != 4:
                issues.append(f"element[{i}].{name} uv 不是四元组")
                continue
            x1, y1, x2, y2 = uv
            if x1 > x2 or y1 > y2:
                issues.append(f"element[{i}].{name} uv 反向 ({uv})")
            if max(x1, x2) > rw or max(y1, y2) > rh:
                issues.append(f"element[{i}].{name} uv 超出分辨率 {rw}x{rh}: {uv}")

    referenced = set()
    for grp in data.get("outliner") or []:
        for child in grp.get("children") or []:
            if isinstance(child, int):
                referenced.add(child)
            elif isinstance(child, dict):
                referenced.add(-1)
    dangling = [i for i in referenced if i >= len(elements) or i < 0]
    if dangling:
        issues.append(f"outliner 引用了不存在的 element: {dangling}")

    return {
        "path": str(p),
        "cubes": len(elements),
        "groups": len(data.get("outliner") or []),
        "resolution": [rw, rh],
        "ok": not issues,
        "issues": issues,
    }
