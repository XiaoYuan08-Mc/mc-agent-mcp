"""Install artifacts (mods / resource packs / shader packs) into an instance."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from .instances import Instance, InstanceError

TARGETS = {
    "mod": "mods",
    "resourcepack": "resourcepacks",
    "shaderpack": "shaderpacks",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(path: Path) -> str:
    if not path.exists():
        raise InstanceError(f"文件不存在: {path}")
    suffix = path.suffix.lower()
    if suffix == ".mrpack":
        return "modpack"
    if suffix == ".jar":
        return "mod"
    if suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "modrinth.index.json" in names:
                return "modpack"
            if "pack.mcmeta" in names:
                if any(n.startswith("shaders/") for n in names):
                    return "shaderpack"
                return "resourcepack"
            if any(n.endswith("mods.toml") or n == "fabric.mod.json" for n in names):
                return "mod"
        return "resourcepack"
    raise InstanceError(f"不支持的产物类型: {path.name}")


def _mod_meta(path: Path) -> dict:
    """Best-effort fabric/quilt/forge metadata read."""
    try:
        with zipfile.ZipFile(path) as zf:
            for candidate in ("fabric.mod.json", "quilt.mod.json"):
                if candidate in zf.namelist():
                    raw = json.loads(zf.read(candidate).decode("utf-8", "replace"))
                    if candidate == "quilt.mod.json":
                        raw = raw.get("quilt_loader", {})
                    return {
                        "id": raw.get("id"),
                        "version": raw.get("version"),
                        "depends": raw.get("depends") or {},
                    }
    except Exception:
        pass
    return {}


def install(inst: Instance, artifact: str | Path, kind: str | None = None) -> dict:
    src = Path(artifact).expanduser().resolve()
    detected = kind or classify(src)
    if detected == "modpack":
        raise InstanceError(
            ".mrpack 不能装进现有实例；把它当独立实例启动（或交给启动器导入）。"
            "mc_install 只处理 mod / 资源包 / 光影包。"
        )
    if detected not in TARGETS:
        raise InstanceError(f"未知产物类别: {detected}")

    dest_dir = inst.dir / TARGETS[detected]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    replaced = False
    if dest.exists():
        backup = dest.with_suffix(dest.suffix + ".bak")
        shutil.copy2(dest, backup)
        dest.unlink()
        replaced = True
    shutil.copy2(src, dest)

    receipt = {
        "instance": inst.name,
        "kind": detected,
        "file": str(dest),
        "sha256": _sha256(dest),
        "size": dest.stat().st_size,
        "replaced": replaced,
        "warnings": [],
    }

    if detected == "mod":
        meta = _mod_meta(dest)
        receipt["mod"] = meta
        deps = meta.get("depends") or {}
        needs_api = any(str(k).lower() == "fabric-api" for k in deps)
        if needs_api:
            present = any("fabric-api" in p.name.lower() or "fabric_api" in p.name.lower()
                          for p in (inst.dir / "mods").glob("*.jar"))
            if not present:
                receipt["warnings"].append(
                    "该 mod 依赖 fabric-api，但实例 mods/ 里没有检测到 fabric-api，"
                    "启动前请先安装它。"
                )
    return receipt


def list_installed(inst: Instance) -> dict:
    out = {}
    for kind, sub in TARGETS.items():
        folder = inst.dir / sub
        out[kind] = sorted(p.name for p in folder.glob("*") if p.is_file()
                           and not p.name.endswith(".bak")) if folder.exists() else []
    return {"instance": inst.name, **out}
