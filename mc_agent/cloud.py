"""外部服务的能力边界。

社区市场（发布、四库浏览、产物下载）、联网搜索、专有图像/三维网关都需要远端服务
与凭据，本实现不内置这些端点。这类调用显式返回 `capability_unavailable`，
并给出可执行的本地替代，而不是假装成功。
"""

from __future__ import annotations

from . import state


def unavailable(capability: str, detail: str, alternatives: list[str]) -> dict:
    return {
        "ok": False,
        "capability": capability,
        "error": "capability_unavailable",
        "detail": detail,
        "alternatives": alternatives,
        "checked": state.now(),
    }


def publish(artifact_path: str, title: str = "", description: str = "") -> dict:
    return unavailable(
        "publish_to_community",
        f"本实现不接社区发布服务，没有可写目标。",
        [
            "export_asset(format='resourcepack'|'mcaddon'|'glb') 拿到本地可分发文件",
            "modpack_build 生成 .mrpack，自行上传到 Modrinth/CurseForge",
            "把 export 出来的 zip 直接发给用户，或放进 git 仓库",
        ],
    )


def community_browse(query: str = "", content_type: str = "mod", sort: str = "relevance",
                     limit: int = 20, post_id: str = "") -> dict:
    note = "社区四库（mod/整合包/光影/材质）由远端服务提供，本实现不接入。"
    return {
        **unavailable("community_browse", note,
                      [
                          "mc_search_content(query, mc_version, loader) 走 Modrinth 公开 API，能拿到 slug/下载链接/依赖",
                          "modpack(action='search') 同源，能直接落到 .mrpack",
                      ]),
        "echo": {"query": query, "content_type": content_type, "sort": sort,
                 "limit": limit, "post_id": post_id},
    }


def community_fetch(post_id: str, what: str = "all", dest_dir: str = "") -> dict:
    return unavailable(
        "community_fetch",
        f"post {post_id} 的产物托管在远端，本实现没有缓存也没有下载凭据。",
        [
            "如果对方给了直链，用 terminal 的 curl/Invoke-WebRequest 下载到 workspace",
            "modpack(action='build', version_id=...) 用 Modrinth 的 version_id 直接拼包",
        ],
    )


def web_search(query: str, scope: str = "minecraft", language: str = "auto",
               minecraft_version: str = "", loader: str = "",
               mod_hint: str = "", max_results: int = 8) -> dict:
    return {
        **unavailable(
            "web_search",
            f"本实现不接搜索服务（不内置搜索 broker），不冒充有搜索结果。",
            [
                "宿主 agent 自带的联网搜索（Claude Code / Cursor / WorkBuddy 的 WebSearch）优先级更高，直接用它",
                "查 Modrinth 元数据用 mc_search_content，不消耗搜索额度",
                "查版本/加载器版本用 mc_runtime(ensure) 或 resolve 系列，信息源是官方 meta",
            ],
        ),
        "echo": {"query": query, "scope": scope, "language": language,
                 "minecraft_version": minecraft_version, "loader": loader,
                 "mod_hint": mod_hint, "max_results": max_results},
    }
