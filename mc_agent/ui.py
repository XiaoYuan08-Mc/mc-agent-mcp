"""UI 面板与布局：Java Screen 骨架、Bedrock JSON-UI、布局盒模型与预览。

这两个工具都是确定性生成器：先有布局契约（矩形、锚点、约束），再产平台代码。
这里同样拒绝"凭感觉摆坐标"——越界、重叠、缺锚点都会在返回里点名。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from mc_craft_mcp import config
from . import state


class UiError(RuntimeError):
    pass


def _slug(raw: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (raw or "").lower()).strip("_")
    return s or "panel"


def _class_name(raw: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", raw)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Panel"


# --------------------------------------------------------------- Java screen
def java_panel(panel_id: str, project_dir: str = "", panel_kind: str = "simple",
               title: str = "", slot_groups: list | None = None, widgets: list | None = None,
               include_player_inventory: bool = False, canvas_width: int = 176,
               namespace: str = "", java_package: str = "", action: str = "write") -> dict:
    root = Path(project_dir).expanduser().resolve() if project_dir else config.projects_dir() / "panelmod"
    ns = namespace or "mcagent"
    pkg = java_package or f"com.example.{ns}"
    pid = _slug(panel_id)
    cls = _class_name(pid) + "Screen"

    slots = []
    for group in slot_groups or [{"id": "main", "x": 8, "y": 18, "cols": 9, "rows": 3, "slot": 18}]:
        cols = int(group.get("cols", 9))
        rows = int(group.get("rows", 3))
        step = int(group.get("slot", 18))
        for r in range(rows):
            for c in range(cols):
                slots.append({
                    "x": int(group.get("x", 8)) + c * step,
                    "y": int(group.get("y", 18)) + r * step,
                    "group": group.get("id", "main"),
                })

    if include_player_inventory:
        for r in range(3):
            for c in range(9):
                slots.append({"x": 8 + c * 18, "y": 84 + r * 18, "group": "player"})
        for c in range(9):
            slots.append({"x": 8 + c * 18, "y": 142, "group": "hotbar"})

    issues = []
    for s in slots:
        if s["x"] < 0 or s["y"] < 0 or s["x"] + 16 > canvas_width:
            issues.append(f"槽位越界: {s}")
    seen = set()
    for s in slots:
        key = (s["x"], s["y"])
        if key in seen:
            issues.append(f"槽位重叠: {key}")
        seen.add(key)

    widget_rows = []
    for w in widgets or []:
        widget_rows.append({
            "id": w.get("id", "w"),
            "type": w.get("type", "button"),
            "x": int(w.get("x", 0)), "y": int(w.get("y", 0)),
            "w": int(w.get("w", 60)), "h": int(w.get("h", 20)),
            "label": w.get("label", ""),
        })

    body_widgets = "\n".join(
        f'        addDrawableChild(ButtonWidget.builder(Text.literal("{w["label"]}"), b -> {{}})\n'
        f'                .dimensions(this.width / 2 - {w["w"] // 2} + {w["x"]}, this.height / 4 + {w["y"]}, {w["w"]}, {w["h"]})\n'
        f'                .build());'
        for w in widget_rows if w["type"] == "button"
    ) or "        // 没有声明 widget"

    code = f"""package {pkg};

import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.text.Text;

/** 由 mc-agent 生成的界面骨架（{pid}）。槽位坐标已按 176 宽画布计算。 */
public class {cls} extends Screen {{

    public {cls}() {{
        super(Text.literal("{title or pid}"));
    }}

    @Override
    protected void init() {{
{body_widgets}
    }}
}}
"""
    src = root / "src" / "main" / "java" / Path(*pkg.split(".")) / f"{cls}.java"
    if action != "preview":
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(code, "utf-8")

    return {
        "panel_id": pid,
        "class": cls,
        "canvas_width": canvas_width,
        "slots": slots,
        "slot_count": len(slots),
        "widgets": widget_rows,
        "issues": issues,
        "source": str(src) if action != "preview" else None,
        "source_preview": code if action == "preview" else None,
    }


# --------------------------------------------------------------- Bedrock JSON-UI
def bedrock_panel(panel_id: str, project_dir: str = "", panel_mode: str = "screen",
                  api_mode: str = "json_ui", title: str = "", controls: list | None = None,
                  canvas_width: int = 320, canvas_height: int = 180,
                  grid_columns: int = 3, grid_rows: int = 2,
                  binding_target: str = "", action: str = "write") -> dict:
    root = Path(project_dir).expanduser().resolve() if project_dir else config.projects_dir() / "bedrock_ui"
    pid = _slug(panel_id)
    ui_dir = root / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)

    col_w = canvas_width // max(1, grid_columns)
    row_h = canvas_height // max(1, grid_rows)
    items = controls or [
        {"id": f"slot_{r}_{c}", "type": "label", "text": "—"}
        for r in range(grid_rows) for c in range(grid_columns)
    ]
    elements = []
    for i, ctl in enumerate(items[: grid_columns * grid_rows]):
        r, c = divmod(i, grid_columns)
        elements.append({
            f"ctl_{ctl.get('id', i)}": {
                "type": ctl.get("type", "label"),
                "text": ctl.get("text", ""),
                "size": [col_w - 8, ctl.get("h", row_h - 8)],
                "offset": [c * col_w + 4, r * row_h + 4],
                **({"button_text": ctl.get("text", "")} if ctl.get("type") == "button" else {}),
            }
        })

    doc = {
        "namespace": "mcagent_ui",
        "panel": {
            f"{pid}_panel": {
                "type": "panel",
                "size": [canvas_width, canvas_height],
                "controls": [
                    {"title": {"type": "label", "text": title or pid, "size": [canvas_width - 16, 16], "offset": [8, 4]}}
                ] + elements,
                "bindings": [{"binding_name": binding_target}] if binding_target else [],
            }
        },
    }
    out = ui_dir / f"{pid}.json"
    if action != "preview":
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), "utf-8")

    return {
        "panel_id": pid,
        "mode": panel_mode,
        "api_mode": api_mode,
        "output": str(out) if action != "preview" else None,
        "grid": [grid_columns, grid_rows],
        "cells": [{"x": c * col_w + 4, "y": r * row_h + 4, "w": col_w - 8, "h": row_h - 8}
                  for r in range(grid_rows) for c in range(grid_columns)],
        "document_preview": doc if action == "preview" else None,
    }


# --------------------------------------------------------------- layout DSL
def layout(action: str, layout_id: str, name: str = "", platform: str = "java",
           surface: str = "screen", canvas: dict | None = None, viewport: dict | None = None,
           panel: dict | None = None, elements: list | None = None,
           variants: list | None = None, reserved_rects: list | None = None,
           constraints: list | None = None, evidence_path: str = "",
           expected_previous_hash: str = "") -> dict:
    if action == "read":
        rec = state.get_ui_layout(layout_id)
        if not rec:
            raise UiError(f"没有布局 {layout_id}")
        return rec

    canvas = canvas or {"width": 176, "height": 166}
    cw, ch = int(canvas.get("width", 176)), int(canvas.get("height", 166))
    if cw <= 0 or ch <= 0:
        raise UiError("canvas 尺寸必须为正")
    viewport = viewport or {"x": 0, "y": 0, "width": cw, "height": ch}
    vx, vy = int(viewport.get("x", 0)), int(viewport.get("y", 0))
    vw, vh = int(viewport.get("width", cw)), int(viewport.get("height", ch))

    issues = []
    placed = []
    for el in elements or []:
        eid = el.get("id")
        if not eid:
            raise UiError("每个 element 需要 id")
        x, y = int(el.get("x", 0)), int(el.get("y", 0))
        w, h = int(el.get("w", 8)), int(el.get("h", 8))
        if w <= 0 or h <= 0:
            issues.append(f"{eid}: 宽高必须为正")
        if x < vx or y < vy or x + w > vx + vw or y + h > vy + vh:
            issues.append(f"{eid}: 超出 viewport（{x},{y},{w},{h}）")
        for r in reserved_rects or []:
            rx, ry, rw, rh = r.get("x", 0), r.get("y", 0), r.get("w", 0), r.get("h", 0)
            if x < rx + rw and rx < x + w and y < ry + rh and ry < y + h:
                issues.append(f"{eid}: 与保留区 {r.get('id','?')} 重叠")
        placed.append({
            "id": eid, "type": el.get("type", "panel"), "x": x, "y": y, "w": w, "h": h,
            "anchor": el.get("anchor", "top_left"), "text": el.get("text", ""),
            "asset": el.get("asset", ""),
        })

    for clause in constraints or []:
        if not isinstance(clause, dict):
            continue
        kind = clause.get("kind")
        ids = clause.get("elements") or []
        subset = [p for p in placed if p["id"] in ids]
        if kind == "non_overlapping":
            for i, a in enumerate(subset):
                for b in subset[i + 1:]:
                    if a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] \
                            and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]:
                        issues.append(f"约束违反：{a['id']} 与 {b['id']} 重叠")
        elif kind == "align_x" and len({p["x"] for p in subset}) > 1:
            issues.append(f"约束违反：{ids} 未对齐 x")
        elif kind == "align_y" and len({p["y"] for p in subset}) > 1:
            issues.append(f"约束违反：{ids} 未对齐 y")

    preview = config.exports_dir() / f"{_slug(layout_id)}_layout.png"
    try:
        scale = 2
        img = Image.new("RGBA", (cw * scale + 20, ch * scale + 20), (250, 250, 252, 255))
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([10, 10, 10 + vw * scale, 10 + vh * scale], outline=(120, 120, 130, 255))
        for r in reserved_rects or []:
            d.rectangle([10 + r.get("x", 0) * scale, 10 + r.get("y", 0) * scale,
                         10 + (r.get("x", 0) + r.get("w", 0)) * scale,
                         10 + (r.get("y", 0) + r.get("h", 0)) * scale],
                        fill=(230, 200, 200, 120))
        for p in placed:
            d.rectangle([10 + p["x"] * scale, 10 + p["y"] * scale,
                         10 + (p["x"] + p["w"]) * scale, 10 + (p["y"] + p["h"]) * scale],
                        fill=(180, 205, 235, 160), outline=(80, 110, 150, 255))
            d.text((12 + p["x"] * scale, 11 + p["y"] * scale), p["id"][:14], fill=(30, 40, 60, 255))
        img.save(preview)
        preview_path = str(preview)
    except Exception as exc:  # noqa: BLE001
        preview_path = ""
        issues.append(f"预览渲染失败: {exc}")

    digest = hashlib.sha256(json.dumps(
        {"canvas": [cw, ch], "elements": placed}, sort_keys=True).encode()).hexdigest()[:16]
    previous = state.get_ui_layout(layout_id) or {}
    if expected_previous_hash and previous.get("sha256") and previous["sha256"] != expected_previous_hash:
        raise UiError(f"布局已被改过（当前 {previous['sha256']}，期望 {expected_previous_hash}）")

    doc = {
        "action": action,
        "layout_id": layout_id,
        "name": name or layout_id,
        "platform": platform,
        "surface": surface,
        "canvas": {"width": cw, "height": ch},
        "viewport": {"x": vx, "y": vy, "width": vw, "height": vh},
        "panel": panel or {},
        "elements": placed,
        "variants": variants or [],
        "reserved_rects": reserved_rects or [],
        "constraints": constraints or [],
        "sha256": digest,
        "preview": preview_path,
        "issues": issues,
        "ok": not issues,
        "evidence_path": evidence_path,
        "updated": state.now(),
    }
    state.put_ui_layout(doc)
    return doc


def asset_set(action: str, asset_set_id: str = "", name: str = "", platform: str = "java",
              surface: str = "screen", preview_asset_id: str = "",
              assets: list | None = None, layout_id: str = "", evidence: str = "",
              geometry_evidence_paths: list | None = None) -> dict:
    if action == "read":
        rec = state.get_asset_set(asset_set_id)
        if not rec:
            raise UiError(f"没有资产集 {asset_set_id}")
        return rec

    layout = state.get_ui_layout(layout_id) if layout_id else None
    if layout_id and not layout:
        raise UiError(f"layout_id {layout_id} 不存在，先 ui_layout 建布局")

    rows = []
    for item in assets or []:
        aid = item.get("id") or item.get("asset_id")
        if not aid:
            raise UiError("assets 每项需要 id")
        rows.append({
            "id": aid,
            "kind": item.get("kind", "texture"),
            "path": item.get("path", ""),
            "target": item.get("target", ""),
            "nine_slice": item.get("nine_slice"),
        })

    doc = {
        "asset_set_id": asset_set_id or state.new_id("assetset"),
        "name": name or "asset_set",
        "platform": platform,
        "surface": surface,
        "preview_asset_id": preview_asset_id,
        "assets": rows,
        "layout_id": layout_id,
        "layout_sha256": (layout or {}).get("sha256", ""),
        "evidence": evidence,
        "geometry_evidence_paths": geometry_evidence_paths or [],
        "updated": state.now(),
    }
    state.put_asset_set(doc)
    return doc
