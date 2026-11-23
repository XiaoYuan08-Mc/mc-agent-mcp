"""Packaging: resource packs (.zip) and modpacks (.mrpack / Modrinth index)."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from . import config, resolve

SKIP_DIRS = {".git", ".gradle", "build", "dist", "node_modules", "__pycache__"}


class PackError(RuntimeError):
    pass


def _iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if set(rel.parts[:-1]) & SKIP_DIRS or rel.parts[0] in SKIP_DIRS:
            continue
        yield p, rel.as_posix()


def resourcepack_build(pack_dir: str, output: str = "", compression: int = 9) -> dict:
    root = Path(pack_dir).expanduser().resolve()
    if not root.is_dir():
        raise PackError(f"目录不存在: {root}")
    meta_path = root / "pack.mcmeta"
    if not meta_path.exists():
        raise PackError("缺少 pack.mcmeta（资源包必须在根目录带 pack.mcmeta）")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        raise PackError(f"pack.mcmeta 不是合法 JSON: {exc}") from exc
    pack = meta.get("pack") or {}
    if not isinstance(pack.get("pack_format"), int):
        raise PackError("pack.mcmeta 里的 pack.pack_format 必须是整数")
    if not (root / "assets").exists():
        raise PackError("缺少 assets/ 目录，资源包没有可加载内容")

    out = Path(output).expanduser().resolve() if output else config.exports_dir() / f"{root.name}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=compression) as zf:
        for src, rel in _iter_files(root):
            zf.write(src, rel)
            count += 1
    return {
        "output": str(out),
        "files": count,
        "size": out.stat().st_size,
        "pack_format": pack["pack_format"],
        "description": pack.get("description"),
    }


def modpack_build(
    name: str,
    mc_version: str,
    mods: list,
    loader: str = "fabric",
    loader_version: str = "",
    overrides_dir: str = "",
    output: str = "",
    summary: str = "",
) -> dict:
    if loader != "fabric":
        raise PackError("modpack 目前只写 fabric loader；Forge/NeoForge 的 loader 版本矩阵未验证，不猜")
    if not loader_version:
        loader_version = resolve.fabric_loader_version(mc_version)

    files: list[dict] = []
    resolved_mods: list[dict] = []
    for item in mods:
        if isinstance(item, str):
            slug = item
            versions = resolve.modrinth_versions(slug, mc_version, loader, limit=5)
            if not versions:
                raise PackError(f"Modrinth 上找不到 {slug} 的 {mc_version}/{loader} 版本")
            chosen = versions[0]
        else:
            slug = item.get("slug")
            want = item.get("version_id")
            versions = resolve.modrinth_versions(slug, mc_version, loader, limit=10)
            chosen = next((v for v in versions if v["id"] == want), None) if want else (
                versions[0] if versions else None)
            if not chosen:
                raise PackError(f"找不到 {slug} 的指定版本 {want}")
        f = chosen.get("file") or {}
        if not f.get("url"):
            raise PackError(f"{slug} 的版本没有可下载文件")
        files.append({
            "path": f"mods/{f['filename']}",
            "hashes": {"sha1": f.get("sha1") or "", "sha512": f.get("sha512") or ""},
            "env": {"client": "required", "server": "required"},
            "downloads": [f["url"]],
            "fileSize": f.get("size") or 0,
        })
        resolved_mods.append({"slug": slug, "version": chosen.get("version_number")})

    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "1.0.0",
        "name": name,
        "summary": summary or f"{name} — {mc_version} / {loader}",
        "files": files,
        "dependencies": {"minecraft": mc_version, "fabric-loader": loader_version},
    }

    out = Path(output).expanduser().resolve() if output else config.exports_dir() / f"{name}.mrpack"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modrinth.index.json", json.dumps(index, ensure_ascii=False, indent=2))
        if overrides_dir:
            root = Path(overrides_dir).expanduser().resolve()
            if not root.is_dir():
                raise PackError(f"overrides 目录不存在: {root}")
            for src, rel in _iter_files(root):
                zf.write(src, f"overrides/{rel}")
    return {
        "output": str(out),
        "size": out.stat().st_size,
        "mc_version": mc_version,
        "loader": loader,
        "loader_version": loader_version,
        "mods": resolved_mods,
        "file_count": len(files),
    }
