"""绑骨：分件 → 语义标注 → 分组 → 运动裁决 → 骨骼聚类。

语义标注需要对三角网格做视觉判断（VLM 看图标注）。本实现没有视觉模型，语义那一步
由调用方（agent / 用户）给出，本模块负责三件事：几何事实、状态机校验、骨骼落地。
好处是不会瞎猜骨骼名——猜错骨骼名只会得到"什么都不动"的动画。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from mc_craft_mcp import config
from . import assets, state


class RigError(RuntimeError):
    pass


PART_COLORS = [
    (232, 92, 92), (92, 168, 232), (110, 202, 132), (232, 186, 82),
    (176, 122, 232), (82, 208, 208), (232, 128, 196), (150, 150, 150),
]


def _geometry_hash(model: dict) -> str:
    h = hashlib.sha256()
    for el in model.get("elements") or []:
        h.update(json.dumps([el.get("name"), el.get("from"), el.get("to")], sort_keys=True).encode())
    for grp in model.get("outliner") or []:
        h.update(json.dumps([grp.get("name"), grp.get("children")], sort_keys=True).encode())
    return h.hexdigest()[:16]


def _bbox_of(model: dict, indices: list[int]) -> dict:
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for i in indices:
        if i >= len(model.get("elements") or []):
            continue
        el = model["elements"][i]
        for axis in range(3):
            lo[axis] = min(lo[axis], el["from"][axis])
            hi[axis] = max(hi[axis], el["to"][axis])
    if lo[0] > 1e8:
        return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0], "centroid": [0, 0, 0]}
    return {
        "min": [round(v, 2) for v in lo],
        "max": [round(v, 2) for v in hi],
        "size": [round(hi[i] - lo[i], 2) for i in range(3)],
        "centroid": [round((hi[i] + lo[i]) / 2, 2) for i in range(3)],
    }


def _highlight_render(model: dict, groups: list[dict], out: Path, size: int = 512) -> str:
    """每个 group 一个色块，输出高亮图，方便人/模型对齐 part_id 与几何。"""
    elements = model.get("elements") or []
    polys = []
    for gi, grp in enumerate(groups):
        color = PART_COLORS[gi % len(PART_COLORS)]
        for idx in grp.get("children") or []:
            if not isinstance(idx, int) or idx >= len(elements):
                continue
            el = elements[idx]
            x1, y1, z1 = el["from"]
            x2, y2, z2 = el["to"]
            pts = [
                (x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2),
                (x1, y2, z1), (x2, y2, z1), (x2, y2, z2), (x1, y2, z2),
            ]
            origin = el.get("origin") or [0, 0, 0]
            rot = el.get("rotation") or [0, 0, 0]
            pts = [assets._rot(p, origin, rot) for p in pts]
            for name, idxs in assets.CORNERS.items():
                quad = [pts[i] for i in idxs]
                depth = sum(sum(p) for p in quad) / 4 + gi * 0.001
                polys.append((depth + gi * 0.01, [assets._project(p) for p in quad], color))
    if not polys:
        raise RigError("模型没有可渲染的立方体")
    polys.sort(key=lambda t: t[0])
    flat = [p for _, poly, _ in polys for p in poly]
    minx = min(p[0] for p in flat); maxx = max(p[0] for p in flat)
    miny = min(p[1] for p in flat); maxy = max(p[1] for p in flat)
    span = max(maxx - minx, maxy - miny, 0.001)
    scale = (size - 60) / span
    img = Image.new("RGBA", (size, size), (250, 250, 252, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    for _, poly, color in polys:
        pts = [((x - minx) * scale + 30, (y - miny) * scale + 30) for x, y in poly]
        draw.polygon(pts, fill=color + (235,), outline=(20, 20, 24, 90))
    legend_y = 6
    for gi, grp in enumerate(groups[:10]):
        draw.rectangle([6, legend_y, 16, legend_y + 10], fill=PART_COLORS[gi % len(PART_COLORS)] + (255,))
        draw.text((20, legend_y), str(grp.get("name"))[:28], fill=(20, 20, 24, 255))
        legend_y += 13
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


def inspect(asset_id: str = "", part_ids: list | None = None, motion_chain: str = "",
            include_related: bool = False) -> dict:
    rec = state.get_asset(asset_id) if asset_id else state.current_asset()
    if not rec:
        raise RigError("没有当前资产；先 generate_3d_model 或 import_asset")
    model = assets.read_model(rec["path"])
    groups = model.get("outliner") or []
    if not groups:
        raise RigError("模型没有 outliner 分组，无法分件")

    parts = []
    for i, grp in enumerate(groups):
        idxs = [c for c in (grp.get("children") or []) if isinstance(c, int)]
        box = _bbox_of(model, idxs)
        parts.append({
            "part_id": grp.get("name") or f"part{i}",
            "cubes": len(idxs),
            "triangles": len(idxs) * 12,
            "bbox": box,
            "pivot": grp.get("origin") or [0, 0, 0],
        })

    selected = set(part_ids or [])
    if selected:
        unknown = selected - {p["part_id"] for p in parts}
        if unknown:
            raise RigError(f"未知 part_id: {sorted(unknown)}；可用: {[p['part_id'] for p in parts]}")

    receipt_id = state.new_id("inspect")
    highlight = config.exports_dir() / f"{rec['id']}_{receipt_id}_parts.png"
    try:
        _highlight_render(model, groups, highlight)
    except Exception as exc:  # noqa: BLE001
        highlight = None
        render_error = str(exc)
    else:
        render_error = ""

    receipt = {
        "receipt_id": receipt_id,
        "asset_id": rec["id"],
        "geometry_hash": _geometry_hash(model),
        "parts": [p["part_id"] for p in parts],
        "selected": sorted(selected) if selected else [p["part_id"] for p in parts],
        "highlight": str(highlight) if highlight else "",
        "created": state.now(),
    }
    state.put_inspection(rec["id"], {
        "receipt": receipt,
        "parts": parts,
        "motion_chain_hint": motion_chain,
        "include_related": bool(include_related),
    })

    return {
        "asset_id": rec["id"],
        "receipt": receipt,
        "inventory": parts,
        "highlight_image": str(highlight) if highlight else "",
        "render_error": render_error,
        "next": "对每个 part 调 label_mesh_parts 写语义，全部 draft 后 finalize=true",
    }


def label(receipt: dict | str, parts: list, finalize: bool = False) -> dict:
    if isinstance(receipt, str):
        receipt = json.loads(receipt)
    asset_id = receipt.get("asset_id")
    rec = state.get_asset(asset_id)
    if not rec:
        raise RigError("receipt 的 asset_id 不存在")
    model = assets.read_model(rec["path"])
    if _geometry_hash(model) != receipt.get("geometry_hash"):
        raise RigError("几何已变（重新生成/导入过模型），receipt 失效，请重新 inspect_mesh_parts")

    known = set(receipt.get("parts") or [])
    given = {p.get("part_id") for p in parts}
    missing = given - known
    if missing:
        raise RigError(f"未检查过的 part: {sorted(missing)}")
    stale = set(receipt.get("selected") or []) - given
    if stale and finalize:
        raise RigError(f"还没标注的 part: {sorted(stale)}")

    data = state.load()
    insp = data["inspections"].get(asset_id) or {}
    table = insp.get("labels") or {}
    for p in parts:
        if not p.get("role"):
            raise RigError(f"{p.get('part_id')} 缺 role")
        table[p["part_id"]] = {
            "role": p.get("role"),
            "motion_chain": p.get("motion_chain") or "",
            "level": p.get("level"),
            "side": p.get("side") or "center",
            "attachment_kind": p.get("attachment_kind") or "none",
            "attachment_target": p.get("attachment_target") or "",
            "confidence": float(p.get("confidence", 0.8)),
            "crosses_joint": bool(p.get("crosses_joint", False)),
            "finalized": bool(finalize),
            "updated": state.now(),
        }
    insp["labels"] = table
    insp["finalized"] = bool(finalize)
    data["inspections"][asset_id] = insp
    state.save(data)

    risks = []
    if finalize:
        roles = [v["role"] for v in table.values()]
        if len(roles) != len(set(roles)):
            risks.append("存在重复 role，确认是否真的是镜像件")
        for pid, v in table.items():
            if v["confidence"] < 0.5:
                risks.append(f"{pid} 置信度低（{v['confidence']}），建议重新 inspect")
        chains = {v["motion_chain"] for v in table.values() if v["motion_chain"]}
        if not chains:
            risks.append("没有任何 motion_chain，下一步 apply_rig 会退化成单骨")

    return {
        "asset_id": asset_id,
        "labelled": sorted(table),
        "finalized": bool(finalize),
        "soft_risks": risks,
        "next": "finalize 后调 group_mesh_parts 聚类" if finalize else "继续标注剩余 part",
    }


def group(receipt: dict | str, groups: list, asymmetric_part_ids: list | None = None,
          asymmetry_reason: str = "") -> dict:
    if isinstance(receipt, str):
        receipt = json.loads(receipt)
    asset_id = receipt.get("asset_id")
    data = state.load()
    insp = data["inspections"].get(asset_id) or {}
    table = insp.get("labels") or {}
    if not table or not insp.get("finalized"):
        raise RigError("还没 finalize 语义表，先 label_mesh_parts(finalize=true)")

    seen = {}
    for g in groups:
        for member in g.get("members") or []:
            if member not in table:
                raise RigError(f"未知 part: {member}")
            if member in seen:
                raise RigError(f"{member} 同时属于 {seen[member]} 和 {g.get('name')}")
            seen[member] = g.get("name")
    missing = set(table) - set(seen)
    if missing:
        raise RigError(f"这些 part 没分组: {sorted(missing)}")

    payload = {
        "groups": [
            {
                "name": g.get("name"),
                "members": g.get("members"),
                "roles": [table[m]["role"] for m in g.get("members") or []],
                "sides": [table[m]["side"] for m in g.get("members") or []],
            }
            for g in groups
        ],
        "asymmetric": asymmetric_part_ids or [],
        "asymmetry_reason": asymmetry_reason,
        "created": state.now(),
    }
    insp["groups"] = payload
    data["inspections"][asset_id] = insp
    state.save(data)
    return {"asset_id": asset_id, "groups": payload["groups"], "next": "plan_group_motion 逐组裁运动"}


def plan_motion(receipt: dict | str, groups: list) -> dict:
    if isinstance(receipt, str):
        receipt = json.loads(receipt)
    asset_id = receipt.get("asset_id")
    data = state.load()
    insp = data["inspections"].get(asset_id) or {}
    sealed = insp.get("groups") or {}
    if not sealed.get("groups"):
        raise RigError("先 group_mesh_parts 封组")
    names = {g["name"] for g in sealed["groups"]}
    given = {g.get("group") for g in groups}
    if given != names:
        raise RigError(f"必须每个组恰好一条：缺 {sorted(names - given)}，多 {sorted(given - names)}")

    kinds = {"rigid", "articulated", "attachment", "eye", "static"}
    for g in groups:
        kind = (g.get("kind") or "").lower()
        if kind not in kinds:
            raise RigError(f"{g.get('group')}: kind 必须是 {sorted(kinds)}，unknown 不接受")
        if kind == "articulated":
            levels = g.get("levels") or {}
            members = next(x["members"] for x in sealed["groups"] if x["name"] == g["group"])
            if set(levels) != set(members):
                raise RigError(f"{g['group']}: articulated 需要每个成员都有 level")
        elif g.get("levels"):
            raise RigError(f"{g['group']}: 非 articulated 不能带 levels")
        if kind == "attachment" and not g.get("attach_to"):
            raise RigError(f"{g['group']}: attachment 必须声明 attach_to")

    payload = {"plans": groups, "created": state.now()}
    insp["plans"] = payload
    data["inspections"][asset_id] = insp
    state.save(data)
    return {"asset_id": asset_id, "plans": groups, "next": "apply_rig 落地骨骼"}


def apply_rig(receipt: dict | str, bones: list | None = None, splits: list | None = None,
              drop: list | None = None, keep_emissive_eyes: bool = True) -> dict:
    if isinstance(receipt, str):
        receipt = json.loads(receipt)
    asset_id = receipt.get("asset_id")
    rec = state.get_asset(asset_id)
    if not rec:
        raise RigError("asset 不存在")
    data = state.load()
    insp = data["inspections"].get(asset_id) or {}
    table = insp.get("labels") or {}
    plans = (insp.get("plans") or {}).get("plans") or []
    if not table:
        raise RigError("没有语义表，先走 inspect → label → group → plan")

    model = assets.read_model(rec["path"])
    if _geometry_hash(model) != receipt.get("geometry_hash"):
        raise RigError("几何变了，part_id 已指向别的几何，重跑 inspect")

    if bones:
        bone_spec = bones
        manual = True
    else:
        manual = False
        by_chain: dict[str, list] = {}
        for pid, v in table.items():
            chain = v.get("motion_chain") or "root"
            by_chain.setdefault(chain, []).append(pid)
        bone_spec = []
        for chain, members in by_chain.items():
            members_sorted = sorted(
                members,
                key=lambda m: (table[m].get("level") if table[m].get("level") is not None else 99, m),
            )
            for m in members_sorted:
                bone_spec.append({
                    "name": m if len(members_sorted) == 1 else f"{chain}_{m}",
                    "parts": [m],
                    "parent": chain if m != members_sorted[0] else None,
                })

    assigned = {}
    for b in bone_spec:
        for part in b.get("parts") or []:
            if part in assigned:
                raise RigError(f"{part} 被 {assigned[part]} 和 {b['name']} 重复认领")
            if part not in table:
                raise RigError(f"骨骼 {b['name']} 引用了未标注的 part: {part}")
            assigned[part] = b["name"]
    unassigned = set(table) - set(assigned)
    if unassigned:
        raise RigError(f"这些 part 没骨骼认领: {sorted(unassigned)}")

    # 写回 outliner：给 group 加 parent / bone_name，pivot 用 part 质心
    name_to_group = {g.get("name"): g for g in model.get("outliner") or []}
    for b in bone_spec:
        target = name_to_group.get((b.get("parts") or ["/"])[0])
        if not target:
            continue
        target["bone_name"] = b["name"]
        # Blockbench 的层级靠 outliner 嵌套，不认 parent 字段；
        # 这里只记到 bone_name，避免写自引用污染工程文件。
        if b.get("parent") and b["parent"] != b["name"]:
            target["bone_parent"] = b["parent"]

    drops = [d for d in (drop or []) if d in table]
    if keep_emissive_eyes:
        drops = [d for d in drops if "eye" not in (table[d].get("role") or "")]

    out = assets.write_model(model, rec["path"])
    insp["rig"] = {"bones": bone_spec, "manual_override": manual, "drops": drops, "created": state.now()}
    data["inspections"][asset_id] = insp
    state.save(data)

    bone_rows = assets.bones_of(assets.read_model(rec["path"]))
    return {
        "asset_id": asset_id,
        "bones": bone_rows,
        "manual_override": manual,
        "dropped": drops,
        "written": out["output"],
        "validation_ok": out["validation"]["ok"],
        "next": "list_model_bones 确认后 apply_animation",
    }
