"""MCP surface for mc-craft.

Run:
    python -m mc_craft_mcp.server            # stdio (default)
    MCC_TRANSPORT=http python -m mc_craft_mcp.server
"""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import build, config, install, instances, model, pack, resolve, scaffold, textures
from .instances import Instance, InstanceError

mcp = FastMCP(
    name="mc-craft",
    instructions=(
        "Minecraft Java 创造与开发工具集：实例/运行、mod 工程、构建、打包、像素资产。"
        "先看 mc_instance(list) 明确目标版本与 loader，再动手；版本号一律现查，不要猜。"
    ),
)

KNOWN = (InstanceError, resolve.ResolutionError, scaffold.ScaffoldError,
         build.BuildError, pack.PackError, textures.TextureError, model.ModelError)


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KNOWN as exc:
            raise ToolError(str(exc)) from exc
    return wrapper


def _inst(name: str) -> Instance:
    return Instance.load(name)


# ---------------------------------------------------------------- instances
@mcp.tool
@_guard
def mc_instance(
    action: str = "list",
    name: str = "",
    mc_version: str = "",
    loader: str = "vanilla",
    loader_version: str = "",
    notes: str = "",
) -> dict:
    """管理本地 Minecraft 实例：list / create / locate / inspect。

    - list：列出全部实例（不需要其他参数）
    - create：name + mc_version + loader（fabric/vanilla/neoforge…），
      fabric 的 loader_version 留空会自动查最新
    - locate：不传 name 时返回最近创建的实例，用于「当前目标」
    - inspect：返回实例目录、已装内容、运行状态
    """
    action = action.lower()
    if action == "list":
        return {"home": str(config.home()), "instances": instances.list_instances()}
    if action == "create":
        if not name or not mc_version:
            raise ToolError("create 需要 name 和 mc_version")
        inst = instances.create_instance(name, mc_version, loader, loader_version, notes)
        return {"created": inst.to_dict()}
    if action == "locate":
        items = instances.list_instances()
        if not items:
            raise ToolError("还没有任何实例，先 mc_instance(action=create, ...)")
        if name:
            inst = _inst(name)
        else:
            latest = max(items, key=lambda d: d.get("created", ""))
            inst = _inst(latest["name"])
        return {"instance": inst.to_dict(), "status": instances.status(inst)}
    if action == "inspect":
        inst = _inst(name)
        return {
            "instance": inst.to_dict(),
            "status": instances.status(inst),
            "installed": install.list_installed(inst),
        }
    raise ToolError("action 必须是 list / create / locate / inspect")


@mcp.tool
@_guard
def mc_runtime(instance: str, action: str = "status", username: str = "Player") -> dict:
    """实例运行时：status / ensure / launch / stop（底层 PortableMC）。

    - ensure：只下载补全版本+loader，不启动（首次安装必须先用它）
    - launch：后台启动并在 <instance>/logs 写 launcher 日志
    - status：进程是否活着、javapid、日志路径
    - stop：结束该实例的进程树
    """
    inst = _inst(instance)
    action = action.lower()
    if action == "status":
        return instances.status(inst)
    if action == "ensure":
        return instances.ensure_runtime(inst, username)
    if action == "launch":
        return instances.launch(inst, username)
    if action == "stop":
        return instances.stop(inst)
    raise ToolError("action 必须是 status / ensure / launch / stop")


@mcp.tool
@_guard
def mc_logs(instance: str, lines: int = 80, which: str = "latest") -> dict:
    """读实例日志尾部。which=latest 取最新启动日志，which=install 取安装日志。"""
    return instances.tail_log(_inst(instance), lines, which)


# ----------------------------------------------------------------- install
@mcp.tool
@_guard
def mc_install(instance: str, artifact: str, kind: str = "") -> dict:
    """把一个产物装进实例：.jar→mods/，资源包 zip→resourcepacks/，光影 zip→shaderpacks/。

    覆盖前会保留 <同名>.bak。.mrpack 不允许装进现有实例（它是独立整合包）。
    kind 留空自动识别。
    """
    return install.install(_inst(instance), artifact, kind or None)


@mcp.tool
@_guard
def mc_installed(instance: str) -> dict:
    """列出实例里已安装的 mod / 资源包 / 光影。"""
    return install.list_installed(_inst(instance))


@mcp.tool
@_guard
def mc_search_content(query: str, mc_version: str, loader: str = "fabric",
                      limit: int = 10) -> dict:
    """按版本+loader 在 Modrinth 搜索 mod/整合包（只返回元数据，不下载）。"""
    return {"query": query, "results": resolve.modrinth_search(query, mc_version, loader, limit)}


# ------------------------------------------------------------------ project
@mcp.tool
@_guard
def scaffold_mod(
    loader: str,
    mc_version: str,
    mod_id: str,
    dest: str = "",
    name: str = "",
    package: str = "",
    description: str = "",
    include_fabric_api: bool = True,
    with_wrapper: bool = True,
) -> dict:
    """生成可编译的 mod 工程（Fabric / NeoForge）。

    loader、Fabric API、Loom/NeoForge 版本在生成时现查；Forge 未实现（不做猜测）。
    生成后应当立刻 gradle_build 一次证明能编译。
    """
    return scaffold.scaffold_mod(
        loader=loader, mc_version=mc_version, mod_id=mod_id, dest=dest, name=name,
        package=package, description=description,
        include_fabric_api=include_fabric_api, with_wrapper=with_wrapper,
    )


@mcp.tool
@_guard
def gradle_build(project_dir: str, task: str = "build", timeout: int = 900,
                 extra_args: str = "") -> dict:
    """在工程里跑 Gradle（优先 gradlew）。自动选对应 JDK（1.21 需 21，1.20.x 需 17）。"""
    return build.gradle_build(project_dir, task, timeout, extra_args)


# ----------------------------------------------------------------- packaging
@mcp.tool
@_guard
def resourcepack_build(pack_dir: str, output: str = "") -> dict:
    """校验并打包资源包：要求根目录 pack.mcmeta(pack_format 为整数) + assets/。"""
    return pack.resourcepack_build(pack_dir, output)


@mcp.tool
@_guard
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
    """写 .mrpack（zip + modrinth.index.json）。mods 传 Modrinth slug 列表或
    [{"slug": "...", "version_id": "..."}]；url/sha1/sha512/size 由 Modrinth 现查。"""
    return pack.modpack_build(name, mc_version, mods, loader, loader_version,
                              overrides_dir, output, summary)


# ------------------------------------------------------------------- assets
@mcp.tool
@_guard
def block_texture(source: str, output: str = "", size: int = 16, colors: int = 16,
                  alpha_threshold: int = 128, quantize: bool = True) -> dict:
    """把任意图处理成方块纹理：最近邻到 size、中位切分调色板、alpha 二值化，并给出接缝指标。"""
    return textures.block_texture(source, output, size, colors, alpha_threshold, quantize)


@mcp.tool
@_guard
def item_icon(source: str, output: str = "", size: int = 32, remove_background: bool = False,
              background_color: str = "", tolerance: int = 12) -> dict:
    """物品栏图标：最近邻到 size（默认 32），可选按背景色抠除并报告内容包围盒。"""
    return textures.item_icon(source, output, size, remove_background, background_color, tolerance)


@mcp.tool
@_guard
def emissive_mask(base: str, output_dir: str = "", threshold: int = 150,
                  tint: str = "#ffffff", size: int | None = None) -> dict:
    """从成品方块纹理确定性生成自发光 mask + 点亮态贴图（像素级阈值，不重画）。"""
    return textures.emissive_mask(base, output_dir, threshold, tint, size)


@mcp.tool
@_guard
def palette_report(path: str, top: int = 8) -> dict:
    """统计一张贴图的实际色板（去透明像素），用于判断是否符合 MC 有限调色板。"""
    return textures.palette_report(path, top)


# ------------------------------------------------------------------- models
@mcp.tool
@_guard
def bbmodel_write(spec: dict, output: str = "") -> dict:
    """按 cube 树 spec 写 .bbmodel。

    spec:
      {"name": "...", "resolution": 16, "texture": "路径或 data URI（可选）",
       "groups": [{"name": "body", "cubes": [
           {"name": "box", "from": [0,0,0], "to": [16,16,16],
            "origin": [8,8,8], "rotation": [0,0,0], "inflate": 0,
            "uv": {"north": [0,0,16,16], ...}}]}]}
    """
    return model.write_model(spec, output)


@mcp.tool
@_guard
def bbmodel_validate(path: str) -> dict:
    """结构校验 .bbmodel：非正尺寸、面数、UV 反向/越界、outliner 悬空引用。"""
    return model.validate_model(path)


def main() -> None:
    transport = __import__("os").environ.get("MCC_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="http", host="127.0.0.1", port=int(__import__("os").environ.get("MCC_PORT", "8790")))
    else:
        mcp.run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
