"""技能包：读仓库 `skills/` 下的 SKILL.md，把工作流注入会话。

技能是明文 Markdown（frontmatter + 正文 + 可选 references），不依赖任何外部程序。
默认根目录是仓库自带的 `skills/`；用环境变量 `MC_AGENT_SKILLS` 可以指向别处。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ENV_ROOT = "MC_AGENT_SKILLS"


class SkillError(RuntimeError):
    pass


def skills_root() -> Path:
    for hint in (os.environ.get(ENV_ROOT, ""), str(Path(__file__).resolve().parents[1] / "skills")):
        if not hint:
            continue
        p = Path(hint)
        if p.is_dir():
            return p
    raise SkillError(f"找不到技能目录；设置环境变量 {ENV_ROOT} 指向 skills/ 目录")



def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    header = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in header.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def catalog() -> list[dict]:
    root = skills_root()
    rows = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        md = child / "SKILL.md"
        if not md.exists():
            continue
        meta, _ = _frontmatter(md.read_text("utf-8", errors="ignore"))
        refs = [str(p.relative_to(child)).replace("\\", "/")
                for p in child.rglob("*") if p.is_file() and p.name != "SKILL.md"]
        rows.append({
            "skill_id": child.name,
            "name": meta.get("name", child.name),
            "description": meta.get("description", ""),
            "disable_model_invocation": meta.get("disable-model-invocation", ""),
            "files": len(refs),
        })
    return rows


def activate(skill_id: str, resource: str = "", reason: str = "") -> dict:
    root = skills_root()
    folder = root / skill_id
    if not folder.is_dir():
        raise SkillError(f"没有技能 {skill_id}；可用: {[r['skill_id'] for r in catalog()]}")
    md = folder / "SKILL.md"
    if not md.exists():
        raise SkillError(f"{skill_id} 缺 SKILL.md")
    meta, body = _frontmatter(md.read_text("utf-8", errors="ignore"))

    payload = {
        "skill_id": skill_id,
        "reason": reason,
        "frontmatter": meta,
        "body": body,
        "resources": [],
    }
    if resource:
        target = (folder / resource).resolve()
        if not str(target).startswith(str(folder.resolve())):
            raise SkillError("resource 越出技能目录")
        if not target.exists():
            raise SkillError(f"资源不存在: {resource}")
        if target.is_file() and target.suffix.lower() in (".md", ".json", ".txt", ".gradle", ".java", ".kts", ".toml", ".properties", ".yml", ".yaml"):
            payload["resources"].append({
                "path": resource,
                "content": target.read_text("utf-8", errors="ignore"),
            })
        else:
            payload["resources"].append({"path": resource, "content": None,
                                         "note": "非文本资源，只返回路径"})
    else:
        ref_dir = folder / "references"
        if ref_dir.is_dir():
            payload["available_references"] = sorted(
                str(p.relative_to(folder)).replace("\\", "/") for p in ref_dir.rglob("*") if p.is_file())
    return payload


def read_resource(skill_id: str, path: str) -> dict:
    root = skills_root()
    folder = (root / skill_id).resolve()
    target = (folder / path).resolve()
    if not str(target).startswith(str(folder)):
        raise SkillError("路径越界")
    if not target.exists():
        raise SkillError(f"不存在: {path}")
    text = target.read_text("utf-8", errors="ignore") if target.suffix.lower() in (
        ".md", ".json", ".txt", ".gradle", ".java", ".kts", ".toml", ".properties") else None
    return {"path": str(target), "content": text}
