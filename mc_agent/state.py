"""会话状态：当前资产、概念、项目简报、资产台账、验收计划、UI 布局。

这些状态放在会话 JSON 里（内存 + `.mcagent/asset_ctx.json`），
进程一关就散。这里落成单个 JSON 文件，跨进程存活，agent 多次调用能看到前一次的记录。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from mc_craft_mcp import config


def _root() -> Path:
    p = config.home() / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path() -> Path:
    return _root() / "session.json"


def _blank() -> dict:
    return {
        "version": 1,
        "current_asset_id": "",
        "assets": {},
        "concepts": {},
        "brief": {},
        "roster": [],
        "validations": [],
        "ui_layouts": {},
        "asset_sets": {},
        "inspections": {},
    }


def load() -> dict:
    p = _path()
    if not p.exists():
        return _blank()
    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception:
        return _blank()
    base = _blank()
    base.update(data if isinstance(data, dict) else {})
    return base


def save(data: dict) -> dict:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)
    return data


def new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# ------------------------------------------------------------------ assets
def register_asset(path: str, name: str, kind: str, asset_id: str = "", meta: dict | None = None) -> dict:
    data = load()
    aid = asset_id or new_id("asset")
    rec = {
        "id": aid,
        "name": name,
        "path": str(Path(path).resolve()),
        "kind": kind,
        "created": now(),
        "meta": meta or {},
    }
    data["assets"][aid] = rec
    data["current_asset_id"] = aid
    save(data)
    return rec


def current_asset() -> dict | None:
    data = load()
    aid = data.get("current_asset_id")
    if not aid:
        return None
    return data["assets"].get(aid)


def get_asset(asset_id: str) -> dict | None:
    return load()["assets"].get(asset_id)


def set_current(asset_id: str) -> dict:
    data = load()
    if asset_id not in data["assets"]:
        raise KeyError(f"未知 asset_id: {asset_id}")
    data["current_asset_id"] = asset_id
    save(data)
    return data["assets"][asset_id]


# ------------------------------------------------------------------ concepts
def add_concepts(items: list[dict]) -> list[dict]:
    data = load()
    for it in items:
        cid = it.get("concept_id") or new_id("concept")
        it["concept_id"] = cid
        data["concepts"][cid] = it
    save(data)
    return items


def get_concept(concept_id: str) -> dict | None:
    return load()["concepts"].get(concept_id)


# ------------------------------------------------------------------ misc records
def set_brief(brief: dict) -> dict:
    data = load()
    data["brief"] = brief
    save(data)
    return brief


def push_roster(entry: dict) -> list:
    data = load()
    rows = [r for r in data["roster"] if r.get("key") != entry.get("key")]
    rows.append(entry)
    data["roster"] = rows
    save(data)
    return rows


def push_validation(entry: dict) -> list:
    data = load()
    entry = dict(entry, recorded=now())
    data["validations"].append(entry)
    save(data)
    return data["validations"]


def put_ui_layout(layout: dict) -> dict:
    data = load()
    lid = layout.get("layout_id") or new_id("layout")
    layout["layout_id"] = lid
    data["ui_layouts"][lid] = layout
    save(data)
    return layout


def get_ui_layout(layout_id: str) -> dict | None:
    return load()["ui_layouts"].get(layout_id)


def put_asset_set(item: dict) -> dict:
    data = load()
    sid = item.get("asset_set_id") or new_id("assetset")
    item["asset_set_id"] = sid
    data["asset_sets"][sid] = item
    save(data)
    return item


def get_asset_set(set_id: str) -> dict | None:
    return load()["asset_sets"].get(set_id)


def put_inspection(asset_id: str, payload: dict) -> dict:
    data = load()
    data["inspections"][asset_id] = payload
    save(data)
    return payload


def get_inspection(asset_id: str) -> dict | None:
    return load()["inspections"].get(asset_id)


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)
