"""Live metadata resolution: loaders, mappings, Fabric API, Modrinth content.

Everything here is best-effort and network-bound. Every helper either returns a
concrete value or raises ResolutionError with a human-readable reason, so callers
can degrade loudly instead of guessing version numbers.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "mc-craft-mcp/0.1 (local tool)"
FABRIC_META = "https://meta.fabricmc.net"
FABRIC_MAVEN = "https://maven.fabricmc.net"
MODRINTH = "https://api.modrinth.com/v2"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases"


class ResolutionError(RuntimeError):
    pass


def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url: str, timeout: float = 20.0):
    return json.loads(_get(url, timeout))


def fabric_loader_version(mc_version: str) -> str:
    try:
        data = _get_json(f"{FABRIC_META}/v2/versions/loader/{urllib.parse.quote(mc_version)}")
        return data[0]["loader"]["version"]
    except Exception as exc:  # noqa: BLE001
        raise ResolutionError(f"Fabric loader 查询失败 ({mc_version}): {exc}") from exc


def fabric_api_version(mc_version: str) -> str | None:
    try:
        versions = modrinth_versions("fabric-api", mc_version, "fabric", limit=3)
        return versions[0]["version_number"] if versions else None
    except Exception:
        return None


def loom_version(mc_version: str) -> str:
    """Fabric Loom is version-gated: 1.20.x uses 1.7, 1.21.x uses 1.9+."""
    try:
        raw = _get(f"{FABRIC_MAVEN}/net/fabricmc/fabric-loom/maven-metadata.xml")
        root = ET.fromstring(raw)
        releases = [v.text for v in root.iter("version") if v.text and "-" not in v.text]
        minors = sorted({r.split(".")[0] + "." + r.split(".")[1] for r in releases if "." in r})
        preferred = "1.7" if mc_version.startswith("1.20.") else "1.9"
        pool = [r for r in releases if r.startswith(preferred + ".")]
        if pool:
            return max(pool, key=lambda s: [int(x) for x in s.split(".") if x.isdigit()])
        if releases:
            return max(releases, key=lambda s: [int(x) for x in s.split(".") if x.isdigit()])
    except Exception:
        pass
    return "1.7-SNAPSHOT" if mc_version.startswith("1.20.") else "1.9-SNAPSHOT"


def neoforge_version(mc_version: str) -> str:
    """NeoForge 1.21.1 -> 21.1.x, 1.20.6 -> 20.6.x."""
    try:
        raw = _get(f"{NEOFORGE_MAVEN}/net/neoforged/neoforge/maven-metadata.xml")
        root = ET.fromstring(raw)
        all_versions = [v.text for v in root.iter("version") if v.text]
        parts = mc_version.split(".")
        prefix = f"{parts[1]}.{parts[2]}" if len(parts) >= 3 else mc_version
        pool = [v for v in all_versions if v.startswith(prefix + ".") and "-" not in v]
        if not pool:
            raise ResolutionError(f"NeoForge 没有匹配 {mc_version} 的版本前缀 {prefix}")
        return max(pool, key=lambda s: [int(x) for x in s.replace(".", "-").split("-") if x.isdigit()])
    except ResolutionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ResolutionError(f"NeoForge 版本查询失败: {exc}") from exc


def modrinth_search(query: str, mc_version: str, loader: str, limit: int = 10) -> list[dict]:
    facets = json.dumps([[f"versions:{mc_version}"], [f"categories:{loader}"]])
    params = urllib.parse.urlencode({"query": query, "facets": facets, "limit": limit})
    try:
        data = _get_json(f"{MODRINTH}/search?{params}")
    except Exception as exc:  # noqa: BLE001
        raise ResolutionError(f"Modrinth 搜索失败: {exc}") from exc
    hits = []
    for h in data.get("hits", []):
        hits.append(
            {
                "slug": h.get("slug"),
                "title": h.get("title"),
                "description": (h.get("description") or "")[:160],
                "downloads": h.get("downloads"),
                "project_id": h.get("project_id"),
            }
        )
    return hits


def modrinth_versions(slug: str, mc_version: str, loader: str, limit: int = 5) -> list[dict]:
    params = urllib.parse.urlencode(
        {"game_versions": json.dumps([mc_version]), "loaders": json.dumps([loader])}
    )
    try:
        data = _get_json(f"{MODRINTH}/project/{urllib.parse.quote(slug)}/version?{params}")
    except Exception as exc:  # noqa: BLE001
        raise ResolutionError(f"Modrinth 版本查询失败 ({slug}): {exc}") from exc
    out = []
    for v in data[:limit]:
        files = v.get("files") or []
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        out.append(
            {
                "id": v.get("id"),
                "version_number": v.get("version_number"),
                "name": v.get("name"),
                "dependencies": v.get("dependencies") or [],
                "file": None
                if not primary
                else {
                    "url": primary.get("url"),
                    "filename": primary.get("filename"),
                    "size": primary.get("size"),
                    "sha1": (primary.get("hashes") or {}).get("sha1"),
                    "sha512": (primary.get("hashes") or {}).get("sha512"),
                },
            }
        )
    return out
