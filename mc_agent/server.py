"""mc-agent MCP server：我的世界创作/开发工具集（22 个家族 / 50 个工具）。

工具按「资产 → 绑骨 → 贴图 → 物品/界面 → 实例运行 → 发布」的流水线组织。
本地确定性能力直接执行；需要外部服务（社区发布/检索、搜索、生成式图像、游戏内桥接）
显式返回 capability_unavailable，不伪造回执。

Run:
    python -m mc_agent.server
    MCC_TRANSPORT=http python -m mc_agent.server
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mc_craft_mcp import build, config, install, instances, model, pack, resolve, scaffold, textures
from mc_craft_mcp.instances import Instance, InstanceError

from . import assets, blocktex, cloud, docs, emissive, icons, imagegen, javaitem, meshtocubes, rigging, skills, state, ui, wininput

mcp = FastMCP(
    name="mc-agent",
    instructions=(
        "我的世界创作/开发工具集：22 个家族 / 50 个工具（另有 render_inventory）。\n"
        "工作顺序：先 mc_instance(list/locate) 确认目标版本与 loader → 需要工程就 scaffold_mod → "
        "资产走 design_model_concepts → generate_3d_model → apply_rig → apply_animation → export_asset。\n"
        "图像：generate_image 支持 pollinations（免 key，45s/张）/ openai / 本地 SD WebUI / ComfyUI；"
        "出图后接 generate_item_icon 或方块贴图后处理。3D：generate_3d_model(provider='meshy') 需 MESHY_API_KEY，"
        "拿到三角网格后自动 convert_to_cubes 体素化。\n"
        "游戏内：mc_game_test 用 Win32 SendInput 注入键鼠（窗口必须前台，会自动抢焦点），"
        "mc_capture 优先发 F2 让游戏自己存图，兜底 GDI 抓屏。\n"
        "没有工具回执不得声称生成/构建/启动/验证成功。仅发布/社区/搜索三类仍是云端（返回 capability_unavailable）。"
    ),
)

KNOWN = (
    InstanceError, resolve.ResolutionError, scaffold.ScaffoldError, build.BuildError,
    pack.PackError, textures.TextureError, model.ModelError,
    assets.AssetError, blocktex.BlockTexError, emissive.EmissiveError, icons.IconError,
    javaitem.JavaItemError, rigging.RigError, ui.UiError, docs.DocsError, skills.SkillError,
    imagegen.ImageGenError, meshtocubes.MeshError, wininput.InputError,
)


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KNOWN as exc:
            raise ToolError(str(exc)) from exc
        except FileNotFoundError as exc:
            raise ToolError(f"文件不存在: {exc}") from exc
    return wrapper


def _inst(name: str) -> Instance:
    if not name:
        items = instances.list_instances()
        if not items:
            raise ToolError("还没有实例，先 mc_instance(action=create, ...)")
        name = max(items, key=lambda d: d.get("created", ""))["name"]
    return Instance.load(name)


# ============================================================ asset family
@mcp.tool
@_guard
def design_model_concepts(prompt: str, kind: str = "model") -> dict:
    """模型创建第 1 步：给 4 个概念方案（几何契约 + 缩略图），让用户挑一个。

    不依赖图像服务，直接给 4 组可读参数
    （体型/腿长/头身比/调色板/造型说明）+ 等距渲染缩略图。挑中的 concept_id
    就是 generate_3d_model 的几何契约。永远不要让 agent 替用户挑。
    """
    items = assets.concept_specs(prompt, kind)
    return {
        "concepts": items,
        "dir_note": "本地无图像生成；thumbnail 是几何契约的等距预览，不是概念美术图",
        "next": "让用户选一个 concept_id，再调 generate_3d_model(concept_id=...)",
    }


@mcp.tool
@_guard
def generate_3d_model(concept_id: str, wants_animation: bool = True, name: str = "",
                      output: str = "", provider: str = "local", image: str = "",
                      resolution: int = 32, polycount: int = 1000) -> dict:
    """模型创建第 2 步：概念 → cube 模型（默认本地参数化；provider=meshy 走真 image-to-3d）。

    local：概念参数展开成 cube 树，骨骼分组/UV 一次给全，立即可绑骨。
    meshy：把 image（或 concept 的缩略图）丢给 Meshy 出三角网格，再自动跑
      convert_to_cubes 体素化成立方体。需要 MESHY_API_KEY，且要等 1–5 分钟。
    """
    concept = state.get_concept(concept_id)
    if not concept:
        raise assets.AssetError(f"未知 concept_id {concept_id}；先 design_model_concepts")

    if (provider or "local").lower() == "meshy":
        src = image or concept.get("thumbnail") or ""
        if not src:
            raise assets.AssetError("meshy 需要 image 或可用的 concept 缩略图")
        glb = imagegen.meshy_image_to_3d(src, polycount=polycount)
        conv = meshtocubes.convert(glb["output"], resolution=resolution,
                                   name=name or concept.get("style", "mesh"))
        return {
            "asset_id": conv["asset_id"],
            "provider": "meshy",
            "mesh": glb,
            "cubified": conv,
            "next": "texture_3d_model 上色，或 list_model_bones 看骨骼",
        }

    m = assets.model_from_concept(concept, name=name or concept.get("style", "model"))
    written = assets.write_model(m, output)
    rec = state.register_asset(written["output"], m.get("name"), "bbmodel",
                               meta={"concept_id": concept_id, "wants_animation": bool(wants_animation),
                                     "cubes": written["validation"]["cubes"]})
    return {
        "asset_id": rec["id"],
        "provider": "local",
        "output": written["output"],
        "cubes": written["validation"]["cubes"],
        "groups": len(m.get("outliner") or []),
        "validation": written["validation"],
        "bones_ready": True,
        "next": "texture_3d_model 上色，或 list_model_bones 看骨骼后再 apply_animation",
    }


@mcp.tool
@_guard
def texture_3d_model(style_prompt: str = "", reference_image: str = "",
                     resolution: int = 16, palette: list | None = None) -> dict:
    """模型创建第 3 步：给当前模型上贴图（程序化调色板像素图，16×N 色带）。

    没有可用的 retexture 服务时，按语义部位分配色带，
    分辨率取 8–128（Minecraft 风格默认 16）。reference_image 只用于取主色，
    不做风格迁移。
    """
    rec = state.current_asset()
    if not rec:
        raise assets.AssetError("没有当前资产；先生成或导入模型")
    m = assets.read_model(rec["path"])

    pal = palette
    if reference_image:
        try:
            from PIL import Image
            img = Image.open(reference_image).convert("RGB").resize((1, 1), Image.BOX)
            r, g, b = img.getpixel((0, 0))
            pal = ["#%02x%02x%02x" % (r, g, b)] + (pal or [])
        except Exception:
            pass
    m = assets.paint_model(m, style_prompt, resolution, pal)
    written = assets.write_model(m, rec["path"])
    return {
        "asset_id": rec["id"],
        "output": written["output"],
        "texture": "embedded (data:image/png;base64)",
        "resolution": resolution,
        "palette": pal or "default",
        "validation_ok": written["validation"]["ok"],
        "next": "view_3d_model 看一眼，再 export_asset",
    }


@mcp.tool
@_guard
def convert_to_cubes(mesh_path: str = "", resolution: int = 32, solid: bool = False,
                     target_pixels: float = 16.0, out_path: str = "") -> dict:
    """三角网格 → 立方体（真拟合）：GLB/OBJ → 体素化 → 贪心合并 → .bbmodel。

    resolution 控制台阶精度（16 粗 / 32 默认 / 64 细，超过 64 会很慢）。
    solid=true 会把表面体素填成实心（封闭体积，代价是盒子数暴涨）。
    当前资产已经是 .bbmodel 时，退化为"轴对齐校验"，不改几何。
    """
    target = mesh_path
    if not target:
        rec = state.current_asset()
        if not rec:
            raise assets.AssetError("没有可转换的网格：给 mesh_path，或先 import_asset 一个 .glb/.obj")
        if Path(rec["path"]).suffix.lower() in (".glb", ".obj"):
            target = rec["path"]
    if target:
        return meshtocubes.convert(target, resolution=resolution, target_pixels=target_pixels,
                                   solid=solid, out_path=out_path)

    rec = state.current_asset()
    if not rec:
        raise assets.AssetError("没有当前资产")
    m = assets.read_model(rec["path"])
    bad = []
    for el in m.get("elements") or []:
        rot = el.get("rotation") or [0, 0, 0]
        if any(abs(r) > 0.001 for r in rot):
            bad.append(f"{el.get('name')}: 旋转 {rot}（Java 方块模型不支持旋转盒）")
        if any(t <= f for f, t in zip(el["from"], el["to"])):
            bad.append(f"{el.get('name')}: 尺寸非正")
    return {
        "asset_id": rec["id"],
        "already_cubes": True,
        "cubes": len(m.get("elements") or []),
        "issues": bad,
        "ok": not bad,
        "note": "当前是 cube 模型，只做了轴对齐校验；要转三角网格请传 mesh_path",
    }


@mcp.tool
@_guard
def list_model_bones(asset_id: str = "") -> dict:
    """列出当前模型骨骼（名字 / 父级 / pivot / 立方体数）。写关键帧前必须先看。"""
    rec = state.get_asset(asset_id) if asset_id else state.current_asset()
    if not rec:
        raise assets.AssetError("没有当前资产")
    m = assets.read_model(rec["path"])
    bones = assets.bones_of(m)
    if not bones:
        raise assets.AssetError("模型没有 outliner 分组，先 apply_rig 或重新生成")
    return {"asset_id": rec["id"], "bones": bones,
            "note": "骨骼名不是固定词表，以这里的返回为准，不要猜"}


@mcp.tool
@_guard
def apply_animation(name: str, length: float = 1.0, loop: str = "loop",
                    bones: list | None = None) -> dict:
    """把关键帧写进当前模型。旋转单位是度，位移单位是方块。

    bones 每项：{bone, channel: rotation|position|scale, time, vector:[x,y,z]}
    整模竖直位移会被钳到 0（下去穿地、上去像漂浮）。骨骼名错了直接拒，不生成空动画。
    """
    rec = state.current_asset()
    if not rec:
        raise assets.AssetError("没有当前资产")
    m = assets.read_model(rec["path"])
    m = assets.apply_animation(m, name or "idle", length, loop, bones or [])
    written = assets.write_model(m, rec["path"])
    anim = (m.get("animations") or [{}])[-1]
    return {
        "asset_id": rec["id"],
        "animation": anim.get("name"),
        "tracks": len(anim.get("animators") or {}),
        "keyframes": sum(len(a.get("keyframes") or []) for a in (anim.get("animators") or {}).values()),
        "loop": anim.get("loop"),
        "length": anim.get("length"),
        "output": written["output"],
        "next": "export_asset(format='geckolib') 导出，或 view_3d_model 预览静态姿态",
    }


@mcp.tool
@_guard
def export_asset(asset_name: str = "", format: str = "bbmodel", entity_base: str = "",
                 dest_path: str = "", namespace: str = "mcagent",
                 emissive_part_ids: list | None = None, pixel_grain: int = 16,
                 mc_version: str = "1.21.1") -> dict:
    """导出当前模型。format: bbmodel | resourcepack | geckolib | glb | mcaddon(受限)。

    - bbmodel：Blockbench 工程文件（可继续手改）
    - resourcepack：Java 资源包 zip（含模型 + 贴图 + 物品模型）；pack.mcmeta 按
      mc_version 生成（1.21.9+ 写 min_format/max_format，26.3 = 97）
    - geckolib：geo/animations/texture 三件套，直接放 mod 的 assets 目录
    - glb：最小 glTF 2.0 二进制（顶点色，无贴图）
    - mcaddon：只产 geometry + 贴图，行为包/刷怪蛋需自行补（本地不生成实体行为）
    """
    rec = state.current_asset()
    if not rec:
        raise assets.AssetError("没有当前资产")
    m = assets.read_model(rec["path"])
    name = asset_name or m.get("name") or "model"
    fmt = (format or "bbmodel").lower()

    from PIL import Image
    import io as _io
    import base64 as _b64
    tex = None
    raw = ((m.get("textures") or [{}])[0]).get("source") or ""
    if raw.startswith("data:image"):
        tex = Image.open(_io.BytesIO(_b64.b64decode(raw.split(",", 1)[1]))).convert("RGBA")

    out_dir = Path(dest_path).expanduser().resolve() if dest_path else config.exports_dir()

    if fmt == "bbmodel":
        target = out_dir / f"{name}.bbmodel"
        written = assets.write_model(m, str(target))
        path, extra = written["output"], {"validation": written["validation"]}
    elif fmt == "resourcepack":
        target = out_dir / f"{name}_rp.zip"
        r = assets.export_resourcepack(m, str(target), namespace, entity_base, tex,
                                       mc_version=mc_version)
        path, extra = r["output"], {"files": r["files"]}
    elif fmt == "geckolib":
        geo_dir = out_dir / "geckolib" / name
        geo_dir.mkdir(parents=True, exist_ok=True)
        geo = {
            "format_version": "1.12.0",
            "minecraft:geometry": [{
                "description": {"identifier": f"geometry.{name}", "texture_width": 16,
                                "texture_height": 16, "visible_bounds_width": 4,
                                "visible_bounds_height": 4, "visible_bounds_offset": [0, 2, 0]},
                "bones": [{"name": g.get("name"), "pivot": g.get("origin") or [0, 0, 0], "cubes": []}
                          for g in (m.get("outliner") or [])],
            }],
        }
        (geo_dir / f"{name}.geo.json").write_text(json.dumps(geo, ensure_ascii=False, indent=2), "utf-8")
        anims = m.get("animations") or []
        (geo_dir / f"{name}.animation.json").write_text(json.dumps(
            {"format_version": "1.8.0", "animations": {a.get("name"): a for a in anims}},
            ensure_ascii=False, indent=2), "utf-8")
        if tex:
            tex.save(geo_dir / f"{name}.png")
        path, extra = str(geo_dir), {"geo": f"{name}.geo.json", "animations": len(anims)}
    elif fmt == "glb":
        path = assets.export_glb(m, str(out_dir / f"{name}.glb"))
        extra = {"note": "顶点色，无贴图；要贴图请用 resourcepack 或 Blockbench 重导"}
    elif fmt == "mcaddon":
        rp = out_dir / f"{name}_rp"
        (rp / "models" / "entity").mkdir(parents=True, exist_ok=True)
        (rp / "models" / "entity" / f"{name}.geo.json").write_text(json.dumps({
            "format_version": "1.12.0",
            "minecraft:geometry": [{
                "description": {"identifier": f"geometry.{name}", "texture_width": 16, "texture_height": 16},
                "bones": [{"name": g.get("name"), "pivot": g.get("origin") or [0, 0, 0],
                           "cubes": [{"origin": el["from"], "size": [el["to"][i] - el["from"][i] for i in range(3)],
                                      "uv": [0, 0]} for el in
                                     [m["elements"][c] for c in (g.get("children") or []) if isinstance(c, int)]]}
                          for g in (m.get("outliner") or [])],
            }],
        }, ensure_ascii=False, indent=2), "utf-8")
        if tex:
            (rp / "textures" / "entity").mkdir(parents=True, exist_ok=True)
            tex.save(rp / "textures" / "entity" / f"{name}.png")
        path = str(rp)
        extra = {"note": "只产 geometry + 贴图；manifest/实体行为/刷怪蛋未生成"}
    else:
        raise assets.AssetError(f"不支持的 format: {format}")

    return {"asset_id": rec["id"], "format": fmt, "output": path, **extra}


@mcp.tool
@_guard
def import_asset(path: str, asset_id: str = "", convert_mesh: bool = False,
                 resolution: int = 32) -> dict:
    """导入资产。.bbmodel 直接当当前模型；.glb/.obj + convert_mesh=true 走体素化转方块。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise assets.AssetError(f"文件不存在: {p}")
    if p.suffix.lower() in (".glb", ".obj"):
        if convert_mesh:
            conv = meshtocubes.convert(str(p), resolution=resolution, name=p.stem)
            return {"imported": True, "converted": True, **conv}
        info = assets.import_glb_summary(str(p)) if p.suffix.lower() == ".glb" \
            else {"path": str(p), "note": "OBJ 只读了统计"}
        return {"imported": False, **info,
                "hint": "加 convert_mesh=true 会体素化成立方体并注册资产"}
    m = assets.read_model(str(p))
    rec = state.register_asset(str(p), m.get("name") or p.stem, "bbmodel",
                               asset_id=asset_id,
                               meta={"cubes": len(m.get("elements") or [])})
    return {"imported": True, "asset_id": rec["id"], "name": rec["name"],
            "cubes": rec["meta"]["cubes"], "path": rec["path"]}


@mcp.tool
@_guard
def view_3d_model(note: str = "", size: int = 640) -> dict:
    """把当前模型渲染成等距预览图（离线软光栅，能看清造型与配色）。"""
    rec = state.current_asset()
    if not rec:
        raise assets.AssetError("没有当前资产")
    out = config.exports_dir() / f"{rec['id']}_preview.png"
    path = assets.render_model(assets.read_model(rec["path"]), str(out), size=size)
    return {"asset_id": rec["id"], "preview": path, "note": note,
            "note_limit": "这是几何预览，不是游戏内实拍"}


@mcp.tool
@_guard
def item_visual_pipeline(action: str = "plan", asset_id: str = "", category: str = "item",
                         dimensions_blocks: list | None = None, inventory_policy: str = "auto",
                         forward_axis: str = "north", has_dedicated_hand_model: bool = False,
                         texture_resolution: int = 32, source_icon_path: str = "",
                         allow_model_projection_fallback: bool = False,
                         projection_fallback_reason: str = "", dest_path: str = "",
                         namespace: str = "mcagent", bedrock_format_version: str = "1.20.0",
                         notes: str = "", visual_source: str = "model") -> dict:
    """物品视觉编排：分类 → 尺寸校验 → 出图标（或投影）→ 落进资源包目录。

    action=plan 只出计划；action=build 真的产图标/模型文件。平板图标优先用
    generate_item_icon；模型投影只在 allow_model_projection_fallback=true 时做。
    """
    rec = state.get_asset(asset_id) if asset_id else state.current_asset()
    dims = dimensions_blocks or [1, 1, 1]
    issues = []
    if category in ("weapon", "tool") and visual_source == "model_projection" \
            and not allow_model_projection_fallback:
        issues.append("武器/工具的平板图标应走 generate_item_icon；模型投影需要显式允许")
    if any(d > 3 for d in dims):
        issues.append(f"尺寸 {dims} 超过常见手持体积，确认是不是方块")
    if not rec:
        issues.append("没有当前资产：先 generate_3d_model 或 import_asset")

    plan = {
        "action": action,
        "category": category,
        "dimensions_blocks": dims,
        "inventory_policy": inventory_policy,
        "forward_axis": forward_axis,
        "has_dedicated_hand_model": bool(has_dedicated_hand_model),
        "texture_resolution": int(texture_resolution),
        "visual_source": visual_source,
        "issues": issues,
        "ok": not issues,
        "namespace": namespace,
        "bedrock_format_version": bedrock_format_version,
        "notes": notes,
    }
    if action != "build":
        plan["next"] = "确认无误后 action=build"
        return plan
    if issues:
        raise assets.AssetError("；".join(issues))

    produced = {}
    if source_icon_path:
        produced["icon"] = icons.make_icon(source_icon_path, size=int(texture_resolution),
                                           out_path=dest_path or "")
    else:
        out = dest_path or str(config.exports_dir() / f"{rec['id']}_itemicon.png")
        tmp = config.exports_dir() / f"{rec['id']}_pipe_render.png"
        assets.render_model(assets.read_model(rec["path"]), str(tmp), size=512)
        produced["icon"] = icons.make_icon(str(tmp), size=int(texture_resolution), out_path=out,
                                           background_color="#f6f6f8", background_tolerance=8)
    return {**plan, "produced": produced}


# ============================================================ rig family
@mcp.tool
@_guard
def inspect_mesh_parts(asset_id: str = "", part_ids: list | None = None,
                       motion_chain: str = "", include_related: bool = False) -> dict:
    """分件：给出 part 清单（包围盒/质心/三角面数）+ 高亮图 + inspection_receipt。

    按 outliner 分组切分三角网格，并出双视角高亮图
    （cube 模型的自然分件），语义判断留给调用方。receipt 里带几何哈希，
    几何一改就失效，防止 part_id 指错东西。
    """
    return rigging.inspect(asset_id, part_ids, motion_chain, include_related)


@mcp.tool
@_guard
def label_mesh_parts(inspection_receipt: dict, parts: list, finalize: bool = False) -> dict:
    """写语义：每个 part 给 role / motion_chain / level / side / attachment / 置信度。

    receipt 必须是本次几何的；未检查过、缺失、多余的 id 都会拒。
    所有 part 都有 draft 后才允许 finalize=true。
    """
    return rigging.label(inspection_receipt, parts, finalize)


@mcp.tool
@_guard
def group_mesh_parts(inspection_receipt: dict, groups: list,
                     asymmetric_part_ids: list | None = None, asymmetry_reason: str = "") -> dict:
    """把已标注的 part 聚成语义组（core/head/front_left_leg/…），一键覆盖全部 part。

    一个 part 只能进一个组；漏掉或多出都会拒。这里不裁运动。
    """
    return rigging.group(inspection_receipt, groups, asymmetric_part_ids, asymmetry_reason)


@mcp.tool
@_guard
def plan_group_motion(inspection_receipt: dict, groups: list) -> dict:
    """逐组裁运动：kind=rigid|articulated|attachment|eye|static。

    articulated 每个成员都要 level；其它 kind 不许带 levels；attachment 必须给 attach_to。
    kind=unknown 直接拒——回去重新 inspect。
    """
    return rigging.plan_motion(inspection_receipt, groups)


@mcp.tool
@_guard
def apply_rig(inspection_receipt: dict, bones: list | None = None, splits: list | None = None,
              drop: list | None = None, keep_emissive_eyes: bool = True) -> dict:
    """把语义表聚成骨骼树并写回模型（pivot 来自 part 几何）。

    正常路径留空 bones：按 motion_chain + level 自动聚类。手写 bones 只作为
    特殊机械结构的显式覆盖，返回里会标 manual_override。
    """
    return rigging.apply_rig(inspection_receipt, bones, splits, drop, keep_emissive_eyes)


# ============================================================ texture family
@mcp.tool
@_guard
def generate_standard_block_texture(project_dir: str = "", namespace: str = "mcagent",
                                    block_id: str = "", material_prompt: str = "",
                                    resolution: int = 16, face_layout: str = "all",
                                    palette: list | None = None,
                                    stateful_emissive_candidate: bool = False,
                                    canonical_state: str = "", overwrite: bool = False,
                                    dest_path: str = "") -> dict:
    """标准方块贴图：材质关键词 → 程序化像素图 + blockstate/model/item model 全套。

    材质识别：石/土/草/木/木板/金属/玻璃/砖/沙/晶体/羊毛/黑曜石。
    face_layout=all 出单图，top_side_bottom 出三图。产物落地即可进资源包。
    """
    return blocktex.generate_block_texture(
        project_dir, namespace, block_id, material_prompt, resolution, face_layout,
        palette, stateful_emissive_candidate, canonical_state, overwrite, dest_path)


@mcp.tool
@_guard
def publish_standard_block_asset(staging_metadata: dict | str, project_dir: str = "") -> dict:
    """把上一次生成的 staging 记录发布到项目目录，并核对文件是否齐全。"""
    return blocktex.publish_block_asset(staging_metadata, project_dir)


@mcp.tool
@_guard
def generate_image(prompt: str, dest_path: str = "", aspect_ratio: str = "1:1",
                   reference_images: list | None = None, reference_roles: list | None = None,
                   artifact_role: str = "", require_bound_reference: bool = False,
                   pixel_style: bool = True, target_pixel_size: int = 0,
                   isolation_mode: str = "", matte_color: str = "", variant_key: str = "",
                   ui_stage: str = "", ui_layout_id: str = "", ui_target_id: str = "",
                   ui_style_reference: str = "", provider: str = "auto",
                   width: int = 0, height: int = 0, seed: int = 0,
                   negative: str = "") -> dict:
    """生成式绘图：多后端适配（pollinations 免费 / openai / sdwebui / comfyui）。

    provider=auto 时按 OPENAI_API_KEY → 本地 SD WebUI → 本地 ComfyUI → pollinations 顺序探测。
    pollinations 无需 key，但每 IP 45 秒 1 张（设 POLLINATIONS_TOKEN 解除）。
    target_pixel_size>0 会按最近邻缩到该边长，直接能当像素资产用。
    返回里带真实 provider 与落盘路径——拿去喂 generate_item_icon / 方块贴图后处理。
    """
    ratio = (aspect_ratio or "1:1").replace(" ", "")
    w, h = width, height
    if not w or not h:
        try:
            a, b = [float(x) for x in ratio.split(":")[:2]]
            base = 768
            w = int(base * (a / max(a, b)) ** 0.5 * 1.0) or 512
            h = int(base * (b / max(a, b)) ** 0.5 * 1.0) or 512
            if a >= b:
                w, h = int(512 * a / b), 512
            else:
                w, h = 512, int(512 * b / a)
        except Exception:
            w = h = 512
    res = imagegen.generate(prompt, out_path=dest_path, width=w, height=h,
                            provider=provider, seed=seed, negative=negative,
                            pixel_size=int(target_pixel_size or 0))
    res["artifact_role"] = artifact_role
    res["providers"] = {k: v["ready"] for k, v in imagegen.providers().items()}
    return res


@mcp.tool
@_guard
def generate_block_emissive_mask(staging_metadata: dict | str, emissive_mode: str = "threshold",
                                 activation: str = "always", world_light_level: int = 0,
                                 regions: list | None = None, intensity_mode: str = "binary",
                                 decision_reason: str = "", threshold: int = 165) -> dict:
    """从方块贴图提自发光 mask：按亮度阈值（或 regions 指定矩形）挑像素，出灰度图 + manifest。"""
    return emissive.build_mask(staging_metadata, emissive_mode, activation, world_light_level,
                               regions, intensity_mode, threshold)


@mcp.tool
@_guard
def generate_block_emissive_overlay(mask_manifest: dict | str, state_change: str = "",
                                    face_edits: list | None = None,
                                    detail_density: str = "", nano_model: str = "",
                                    glow_color: list | None = None) -> dict:
    """按 mask 生成点亮态 overlay（mask 区域重新上色 + 提亮），并写 manifest。"""
    return emissive.build_overlay(mask_manifest, state_change, face_edits, glow_color)


@mcp.tool
@_guard
def generate_item_icon(asset_id: str = "", background_color: str = "",
                       background_tolerance: int = 10, design_prompt: str = "",
                       overwrite: bool = False, expected_existing_sha256: str = "",
                       size: int = 32, source_path: str = "",
                       output: str = "") -> dict:
    """32px 物品图标：从当前模型渲染或读图片，抠背景 + 内容包围盒 + 调色板量化。"""
    src = source_path
    if not src:
        rec = state.get_asset(asset_id) if asset_id else state.current_asset()
        if not rec:
            raise icons.IconError("没有源文件：给 source_path，或先有当前模型")
        src = rec["path"]
    return icons.make_icon(src, out_path=output, size=size, background_color=background_color,
                           background_tolerance=background_tolerance)


@mcp.tool
@_guard
def render_inventory(asset_id: str = "", size: int = 64, output: str = "") -> dict:
    """把当前模型渲染成 64×64 背包位图（最近邻，像素风）。"""
    rec = state.get_asset(asset_id) if asset_id else state.current_asset()
    if not rec:
        raise icons.IconError("没有当前资产")
    return icons.render_inventory(rec["path"], output, size)


# ============================================================ runtime family
@mcp.tool
@_guard
def mc_instance(action: str = "list", name: str = "", mc_version: str = "",
                loader: str = "vanilla", loader_version: str = "", notes: str = "") -> dict:
    """实例管理：list / create / locate / inspect。

    create 需要 name + mc_version（loader 可选 vanilla/fabric/neoforge/quilt）；
    locate 不传 name 时返回最近创建的实例；inspect 给目录、已装内容、进程状态。
    """
    act = (action or "list").lower()
    if act == "list":
        return {"home": str(config.home()), "instances": instances.list_instances()}
    if act == "create":
        if not name or not mc_version:
            raise ToolError("create 需要 name 和 mc_version")
        inst = instances.create_instance(name, mc_version, loader, loader_version, notes)
        return {"created": inst.to_dict()}
    if act == "locate":
        inst = _inst(name)
        return {"instance": inst.to_dict(), "status": instances.status(inst)}
    if act == "inspect":
        inst = _inst(name)
        return {"instance": inst.to_dict(), "status": instances.status(inst),
                "installed": install.list_installed(inst)}
    raise ToolError("action 必须是 list / create / locate / inspect")


@mcp.tool
@_guard
def mc_runtime_prepare(instance: str = "", use_bmclapi: bool = True,
                       timeout_seconds: int = 900) -> dict:
    """只装不发：下载并补齐版本/加载器/资源索引。首次启动前必须先跑这一条。"""
    inst = _inst(instance)
    return instances.ensure_runtime(inst)


@mcp.tool
@_guard
def mc_install(artifact_path: str, target: str = "", instance: str = "",
               minecraft_version: str = "", loader: str = "",
               install_dependencies: bool = False, use_bmclapi: bool = True,
               prepare_timeout_seconds: int = 900) -> dict:
    """把 jar / 资源包 / 光影装进实例（同名文件留 .bak）。装 mod 前建议先 prepare。"""
    inst = _inst(instance)
    return install.install(inst, artifact_path, target or None)


@mcp.tool
@_guard
def mc_launch(version: str = "", watch_seconds: int = 0, action: str = "start",
              instance: str = "", use_bmclapi: bool = True) -> dict:
    """启动 / 停止 / 查看实例。start 会后台起进程并写 launcher 日志。"""
    inst = _inst(instance)
    act = (action or "start").lower()
    if act == "status":
        return instances.status(inst)
    if act == "stop":
        return instances.stop(inst)
    if act == "start":
        res = instances.launch(inst)
        if watch_seconds:
            import time
            time.sleep(min(int(watch_seconds), 60))
            res["after_watch"] = instances.status(inst)
        return res
    raise ToolError("action 必须是 start / stop / status")


@mcp.tool
@_guard
def mc_logs(log: str = "latest", tail: int = 80, instance: str = "") -> dict:
    """读实例日志尾部。log=latest 取最新启动日志，install 取安装日志。"""
    inst = _inst(instance)
    which = "install" if (log or "").lower().startswith("install") else "latest"
    return instances.tail_log(inst, int(tail), which)


@mcp.tool
@_guard
def mc_game_test(action: str = "status", control_id: str = "", x: int = 0, y: int = 0,
                 key: str = "", modifier: str = "", duration_ms: int = 0, button: str = "",
                 text: str = "", yaw_delta: float = 0.0, pitch_delta: float = 0.0,
                 scroll_delta: int = 0, allow_foreground: bool = False,
                 instance: str = "", hwnd: int = 0) -> dict:
    """游戏内注入：键盘 / 鼠标 / 文本，走 Win32 SendInput（不需要装 mod）。

    action: status | focus | key | hold | text | click | move | scroll
    - key：点一次按键（duration_ms 为按住时长），modifier 支持 "shift+ctrl"
    - hold：长按（duration_ms，默认 300）
    - text：逐字 unicode 输入（聊天、命令）
    - click：鼠标键，x 当点击次数，button=left/right/middle
    - move：相对移动 x/y 像素（yaw_delta/pitch_delta 会叠加进来转视角）
    - scroll：滚轮，y=格数（正=上）
    窗口必须在前台；工具会自动抢焦点，抢不到会在 warning 里说。
    """
    win_hwnd = hwnd
    if not win_hwnd and instance:
        try:
            _inst(instance)  # 校验实例存在
            win_hwnd = wininput.find_minecraft()["hwnd"]
        except Exception:
            win_hwnd = 0

    act = (action or "status").lower()
    out = {"action": act}

    if yaw_delta or pitch_delta:
        wininput.focus(wininput.find_minecraft()["hwnd"])
        out["look"] = wininput.mouse_move(int(round(yaw_delta)), int(round(pitch_delta)))
        if act in ("status", "move"):
            out["focused"] = True
            return out

    if act == "scroll" and scroll_delta:
        wininput.focus(wininput.find_minecraft()["hwnd"])
        out["scroll"] = wininput.scroll(scroll_delta)
        return out

    payload = wininput.game_action(
        action=act, key=key, modifier=modifier, text=text,
        duration_ms=duration_ms, button=button or "left",
        x=int(x), y=int(y), hwnd=win_hwnd, focus_first=True)
    out.update(payload)
    out["control_id"] = control_id
    return out


@mcp.tool
@_guard
def mc_capture(caption: str = "", allow_foreground: bool = False,
               instance: str = "", method: str = "auto", out_path: str = "") -> dict:
    """取帧。method=ingame 发 F2 让游戏自己存图；window 用 GDI 抓窗口；auto 先试游戏内。

    游戏内置截图最可靠（读的是真实 GL 帧缓冲）；GDI 抓屏在窗口被遮挡或独占全屏时会得到纯色，
    返回里 uniform_frame=true 就是这种情况。
    """
    mode = (method or "auto").lower()
    attempts = []

    if mode in ("auto", "ingame"):
        try:
            inst = _inst(instance)
            shot_dir = Path(inst.dir) / "screenshots"
            wininput.focus(wininput.find_minecraft()["hwnd"])
            res = wininput.screenshot_live(str(shot_dir))
            res.update({"caption": caption, "method": "ingame"})
            if out_path:
                shutil.copyfile(res["output"], out_path)
                res["copied_to"] = out_path
            return res
        except Exception as exc:  # noqa: BLE001
            attempts.append({"method": "ingame", "error": str(exc)})
            if mode == "ingame":
                raise

    try:
        win = wininput.find_minecraft()
        out = out_path or str(config.exports_dir() / f"cap_{state.new_id('shot')}.png")
        res = wininput.screenshot_window(win["hwnd"], out)
        res.update({"caption": caption, "method": "window", "attempts": attempts})
        return res
    except Exception as exc:  # noqa: BLE001
        attempts.append({"method": "window", "error": str(exc)})
        raise ToolError(f"两种取帧都失败：{json.dumps(attempts, ensure_ascii=False)}")


@mcp.tool
@_guard
def mc_visual_verdict(screenshot_id: str = "", verdict: str = "unknown",
                      checks: list | None = None, observations: list | None = None,
                      viewpoint: str = "", next_action: str = "",
                      blocker_code: str = "") -> dict:
    """记录一次视觉判读（截图 id + 结论 + 观察），落进会话状态供后续引用。"""
    entry = {
        "screenshot_id": screenshot_id,
        "verdict": verdict,
        "checks": checks or [],
        "observations": observations or [],
        "viewpoint": viewpoint,
        "next_action": next_action,
        "blocker_code": blocker_code,
    }
    rows = state.push_validation({"kind": "visual_verdict", **entry})
    return {"recorded": entry, "total": len(rows),
            "note": "这是判读记录，不是自动化截图；截图能力见 mc_capture"}


@mcp.tool
@_guard
def gradle_build(mode: str = "build", project_dir: str = "", timeout_s: int = 900) -> dict:
    """跑 Gradle。mode=build|clean|run|test。自动按 MC 版本挑 JDK（1.20.x→17，1.21.x→21）。"""
    root = project_dir or str(config.projects_dir())
    m = (mode or "build").lower()
    task = {"build": "build", "clean": "clean", "run": "runClient", "test": "test"}.get(m, m)
    if not Path(root).expanduser().exists():
        raise ToolError(f"项目目录不存在: {root}")
    return build.gradle_build(root, task=task, timeout=int(timeout_s))


@mcp.tool
@_guard
def scaffold_mod(mod_id: str, loader: str = "fabric", display_name: str = "",
                 description: str = "", project_dir: str = "",
                 minecraft_version: str = "1.21.1", include_geckolib: bool = False,
                 include_mesh_model: bool = False) -> dict:
    """生成可编译的 Fabric / NeoForge 工程（loader/Loom/Gradle 版本现查）。

    minecraft_version 支持 1.16~1.21.11 的旧命名与 26.1/26.2/26.3 新命名：
    26.x 自动切 JDK 25、Gradle 9、net.fabricmc.fabric-loom（无 mappings）
    或 ModDevGradle 2.x，wrapper 也按目标版本固定。
    include_geckolib 只加依赖备注；include_mesh_model 忽略（本实现只出立方体模型）。
    """
    res = scaffold.scaffold_mod(
        loader=loader.lower(), mc_version=minecraft_version, mod_id=mod_id,
        dest=project_dir or "", name=display_name or mod_id,
        description=description or f"{display_name or mod_id} for Minecraft {minecraft_version}",
    )
    res["geckolib_note"] = ("已标注 GeckoLib 依赖位置" if include_geckolib else "未启用 GeckoLib")
    res["mesh_model_note"] = "网格模型（.glb）不在本地生成能力内" if include_mesh_model else ""
    return res


@mcp.tool
@_guard
def mc_dev_run(action: str = "start", project_dir: str = "") -> dict:
    """开发态运行：start 在工程目录后台跑 gradlew runClient；status/stop 走 pid 文件。"""
    root = Path(project_dir or config.projects_dir()).expanduser().resolve()
    if not root.exists():
        raise ToolError(f"项目目录不存在: {root}")
    pid_file = root / ".mcagent_devrun.pid"
    log_file = root / "run" / "mcagent-devrun.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    act = (action or "start").lower()

    if act == "status":
        if not pid_file.exists():
            return {"running": False, "project_dir": str(root)}
        pid = int(pid_file.read_text().strip() or 0)
        alive = False
        try:
            import psutil
            alive = psutil.pid_exists(pid)
        except Exception:
            alive = False
        return {"running": alive, "pid": pid, "log": str(log_file)}

    if act == "stop":
        if not pid_file.exists():
            return {"stopped": False, "reason": "没有记录 pid"}
        pid = int(pid_file.read_text().strip() or 0)
        try:
            import psutil
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                child.terminate()
            proc.terminate()
            pid_file.unlink(missing_ok=True)
            return {"stopped": True, "pid": pid}
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"停止失败: {exc}")

    gradlew = root / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if not gradlew.exists():
        raise ToolError("没有 gradlew，先 scaffold_mod 或自己加 wrapper")
    with open(log_file, "ab") as fh:
        proc = subprocess.Popen([str(gradlew), "runClient"], cwd=str(root),
                                stdout=fh, stderr=subprocess.STDOUT)
    pid_file.write_text(str(proc.pid))
    return {"started": True, "pid": proc.pid, "log": str(log_file),
            "note": "runClient 会拉起真实客户端窗口；关窗口后进程自行退出"}


@mcp.tool
@_guard
def mc_live_update(action: str = "apply", project_dir: str = "", changed_paths: list | None = None,
                   instance: str = "", artifact_path: str = "",
                   expected_plan_id: str = "", dynamic_paths: list | None = None,
                   content_log_path: str = "") -> dict:
    """热重载落地：把产物或改动拷进实例（mod→mods，资源→resourcepacks）。

    热重载采用文件级更新 + 提示重启，不做进程内替换。
    action=plan 只算要动哪些文件。
    """
    inst = _inst(instance)
    src_list: list[str] = []
    if artifact_path:
        src_list.append(artifact_path)
    for p in (changed_paths or []) + (dynamic_paths or []):
        src_list.append(str(p))
    if not src_list:
        raise ToolError("给 artifact_path 或 changed_paths")

    plan = []
    for item in src_list:
        src = Path(item).expanduser().resolve()
        if not src.exists():
            plan.append({"source": str(src), "error": "不存在"})
            continue
        kind = install.classify(src)
        target_dir = {"mod": inst.mods_dir, "resourcepack": inst.resourcepacks_dir,
                      "shader": inst.shaderpacks_dir}.get(kind)
        plan.append({
            "source": str(src),
            "kind": kind,
            "target": str(target_dir / src.name) if target_dir else "",
            "requires_restart": kind in ("mod", "shader"),
        })

    if (action or "apply").lower() == "plan":
        return {"instance": inst.name, "plan": plan, "applied": False}

    applied = []
    for row in plan:
        if row.get("error") or not row["target"]:
            continue
        dst = Path(row["target"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.copyfile(dst, dst.with_suffix(dst.suffix + ".bak"))
        shutil.copyfile(row["source"], dst)
        applied.append(str(dst))

    receipt = {
        "instance": inst.name,
        "applied": applied,
        "plan_id": expected_plan_id or state.new_id("live"),
        "requires_restart": any(r.get("requires_restart") for r in plan if not r.get("error")),
        "note": "文件已落位；进程内热替换未实现，改动生效需要重启客户端",
        "created": state.now(),
    }
    if content_log_path:
        Path(content_log_path).write_text(json.dumps(receipt, ensure_ascii=False, indent=1), "utf-8")
    return receipt


# ============================================================ item / docs / attachments / skills
@mcp.tool
@_guard
def register_java_items(action: str = "write", dest_path: str = "", namespace: str = "",
                        asset_id: str = "", items: list | None = None,
                        dry_run: bool = False) -> dict:
    """生成 Java 物品注册（Fabric: Registry.register / NeoForge: DeferredRegister）+ 模型 + 语言文件。

    items 每项：{id, name, name_en, stack_size}。贴图取当前模型的渲染图。
    """
    return javaitem.register_items(dest_path, namespace, asset_id, items, action, dry_run)


@mcp.tool
@_guard
def mc_api_docs(topic: str = "", symbols: list | None = None, project_dir: str = "") -> dict:
    """查 MC API 文档（离线语料，标注 since）：Item/Block/BlockEntity/网络/渲染/资源包/配方/GeckoLib。

    给 symbols 精确查，给 topic 模糊查；project_dir 存在时报告工程形态。
    """
    return docs.docs(topic, symbols, project_dir)


@mcp.tool
@_guard
def mc_api_search(query: str, physical_side: str = "both", project_dir: str = "",
                  symbols: list | None = None, max_results: int = 8) -> dict:
    """检索 API 语料，按符号名加权排序；physical_side=client|server|both 过滤物理侧。"""
    return docs.search(query, physical_side, symbols, max_results)


@mcp.tool
@_guard
def attach_reference(attachment_id: str, scope: str = "project", reference_role: str = "style",
                     visual_summary: str = "", observed_subject_count: int = 0,
                     subject_inventory: list | None = None, project_scope: str = "",
                     intended_use: str = "", user_directive: str = "") -> dict:
    """登记一个参考附件（图片/工程），写进会话状态，后续按 id 引用。"""
    entry = {
        "attachment_id": attachment_id, "scope": scope, "role": reference_role,
        "visual_summary": visual_summary, "subject_count": observed_subject_count,
        "subjects": subject_inventory or [], "project_scope": project_scope,
        "intended_use": intended_use, "user_directive": user_directive,
        "recorded": state.now(),
    }
    data = state.load()
    data.setdefault("attachments", {})
    data["attachments"][attachment_id] = entry
    state.save(data)
    return {"registered": entry, "total": len(data["attachments"])}


@mcp.tool
@_guard
def activate_skill(skill_id: str, resource: str = "", reason: str = "") -> dict:
    """激活工作流技能（读仓库 skills/ 下的 SKILL.md）：工作流、纪律、验收清单都在里面。

    resource 可指定 references/ 下的文件；不传则列出可用 references。
    """
    return skills.activate(skill_id, resource, reason)


# ============================================================ modpack / state / panels / ui
@mcp.tool
@_guard
def modpack(action: str = "search", mc_version: str = "", loader: str = "fabric",
            query: str = "performance", limit: int = 10, name: str = "",
            version_id: str = "", pack_summary: str = "", mods: list | None = None,
            include_dependencies: bool = True, dest_path: str = "") -> dict:
    """整合包：action=search 查 Modrinth；action=build 写 .mrpack（只支持 fabric loader）。

    build 的 mods 可以是 Modrinth slug，也可以是 {slug|version_id}；依赖会一起解析。
    """
    act = (action or "search").lower()
    if act == "search":
        if not mc_version:
            raise ToolError("search 需要 mc_version")
        rows = resolve.modrinth_search(query, mc_version, loader, int(limit))
        return {"query": query, "mc_version": mc_version, "loader": loader, "hits": rows}
    if act == "build":
        if not mc_version or not mods:
            raise ToolError("build 需要 mc_version 和 mods")
        out = dest_path or str(config.exports_dir() / f"{name or 'pack'}.mrpack")
        return pack.modpack_build(
            name=name or "pack", mc_version=mc_version, mods=mods, loader=loader,
            loader_version=version_id if version_id and ":" in version_id else "",
            summary=pack_summary, output=out,
        )
    raise ToolError("action 必须是 search / build")


@mcp.tool
@_guard
def asset_roster(needed: list | None = None, not_needed: list | None = None,
                 runtime_behaviours: list | None = None,
                 no_runtime_behaviour: list | None = None) -> dict:
    """资产台账：这一轮需要哪些资产、哪些明确不做、哪些要运行时验证。"""
    entry = {
        "key": state.now()[:16],
        "needed": needed or [],
        "not_needed": not_needed or [],
        "runtime_behaviours": runtime_behaviours or [],
        "no_runtime_behaviour": no_runtime_behaviour or [],
        "recorded": state.now(),
    }
    rows = state.push_roster(entry)
    return {"recorded": entry, "total": len(rows)}


@mcp.tool
@_guard
def validation_plan(scope: str = "project", required_gates: list | None = None,
                    deliverables: list | None = None, acceptance_criteria: list | None = None,
                    stop_conditions: list | None = None) -> dict:
    """本轮验收计划：范围、必须过的闸门、交付物、通过标准、什么情况停手。"""
    entry = {
        "kind": "validation_plan",
        "scope": scope,
        "required_gates": required_gates or [],
        "deliverables": deliverables or [],
        "acceptance_criteria": acceptance_criteria or [],
        "stop_conditions": stop_conditions or [],
    }
    rows = state.push_validation(entry)
    return {"recorded": entry, "total": len(rows),
            "note": "计划是记录，不是证据；每条闸门仍需对应工具回执"}


@mcp.tool
@_guard
def project_brief(action: str = "set", brief_summary: str = "", project_scope: str = "",
                  reference_ids: list | None = None, minimum_asset_count: int = 0,
                  visual_asset_ids: list | None = None, visual_mode: str = "",
                  deliverables: list | None = None,
                  runtime_checks: list | None = None) -> dict:
    """项目协作记录：目标、范围、参考、最少资产数、交付物、运行时检查项。action=set|read。"""
    if (action or "set").lower() == "read":
        return {"brief": state.load().get("brief") or {}}
    brief = {
        "summary": brief_summary,
        "scope": project_scope,
        "references": reference_ids or [],
        "minimum_asset_count": int(minimum_asset_count),
        "visual_assets": visual_asset_ids or [],
        "visual_mode": visual_mode,
        "deliverables": deliverables or [],
        "runtime_checks": runtime_checks or [],
        "updated": state.now(),
    }
    state.set_brief(brief)
    return {"brief": brief}


@mcp.tool
@_guard
def java_panel_pipeline(action: str = "write", panel_id: str = "", project_dir: str = "",
                        panel_kind: str = "simple", title: str = "",
                        slot_groups: list | None = None, widgets: list | None = None,
                        include_player_inventory: bool = False, canvas_width: int = 176,
                        namespace: str = "", java_package: str = "") -> dict:
    """生成 Java Screen 骨架：槽位按 176 宽画布计算，重叠/越界会在 issues 里点名。"""
    return ui.java_panel(panel_id or "panel", project_dir, panel_kind, title, slot_groups,
                         widgets, include_player_inventory, canvas_width, namespace,
                         java_package, action)


@mcp.tool
@_guard
def bedrock_panel_pipeline(action: str = "write", panel_id: str = "", project_dir: str = "",
                           panel_mode: str = "screen", api_mode: str = "json_ui",
                           title: str = "", controls: list | None = None,
                           canvas_width: int = 320, canvas_height: int = 180,
                           grid_columns: int = 3, grid_rows: int = 2,
                           binding_target: str = "") -> dict:
    """生成基岩 JSON-UI 面板（ui/<id>.json），控件按网格自动排布。"""
    return ui.bedrock_panel(panel_id or "panel", project_dir, panel_mode, api_mode, title,
                            controls, canvas_width, canvas_height, grid_columns, grid_rows,
                            binding_target, action)


@mcp.tool
@_guard
def ui_layout(action: str = "write", layout_id: str = "", expected_previous_hash: str = "",
              name: str = "", platform: str = "java", surface: str = "screen",
              canvas: dict | None = None, viewport: dict | None = None,
              panel: dict | None = None, elements: list | None = None,
              variants: list | None = None, reserved_rects: list | None = None,
              constraints: list | None = None, evidence_path: str = "") -> dict:
    """布局 DSL：元素盒模型 + 越界/重叠/约束校验 + PNG 预览。action=write|read|preview。"""
    return ui.layout(action, layout_id or "layout", name, platform, surface, canvas, viewport,
                     panel, elements, variants, reserved_rects, constraints, evidence_path,
                     expected_previous_hash)


@mcp.tool
@_guard
def ui_asset_set(action: str = "write", asset_set_id: str = "", name: str = "",
                 platform: str = "java", surface: str = "screen",
                 preview_asset_id: str = "", assets: list | None = None,
                 layout_id: str = "", layout_sha256: str = "", evidence: str = "",
                 geometry_evidence_paths: list | None = None) -> dict:
    """资产集登记：把图标/九宫格/贴图绑到某个布局上，校验布局存在。action=write|read。"""
    return ui.asset_set(action, asset_set_id, name, platform, surface, preview_asset_id,
                        assets, layout_id, evidence, geometry_evidence_paths)


# ============================================================ cloud boundary
@mcp.tool
@_guard
def publish_to_community(artifact_path: str, title: str = "", description: str = "") -> dict:
    """发布到社区市场。本实现没有可写目标 → capability_unavailable + 替代路径。"""
    return cloud.publish(artifact_path, title, description)


@mcp.tool
@_guard
def community_browse(query: str = "", content_type: str = "mod", sort: str = "relevance",
                     limit: int = 20, post_id: str = "") -> dict:
    """浏览社区四库。本实现不接入社区服务；替代是 Modrinth 检索。"""
    return cloud.community_browse(query, content_type, sort, limit, post_id)


@mcp.tool
@_guard
def community_fetch(post_id: str, what: str = "all", dest_dir: str = "") -> dict:
    """下载社区产物。产物托管在远端，本实现无下载凭据。"""
    return cloud.community_fetch(post_id, what, dest_dir)


@mcp.tool
@_guard
def web_search(query: str, scope: str = "minecraft", language: str = "auto",
               minecraft_version: str = "", loader: str = "", mod_hint: str = "",
               max_results: int = 8) -> dict:
    """联网搜索。本实现不接搜索服务，改用宿主 agent 自带的搜索。"""
    return cloud.web_search(query, scope, language, minecraft_version, loader, mod_hint, max_results)


@mcp.resource("skill://list")
def skill_list() -> str:
    """列出仓库内置的工作流技能（id / 名称 / 文件数）。"""
    rows = skills.catalog()
    return "\n".join(f"{r['skill_id']}\t{r['name']}\t{r['files']} files" for r in rows)


@mcp.resource("skill://{skill_id}")
def skill_doc(skill_id: str) -> str:
    """读某个技能的 SKILL.md 全文（工作流与纪律都在里面）。"""
    payload = skills.activate(skill_id)
    meta = payload.get("frontmatter") or {}
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{head}\n---\n\n{payload['body']}"


def main() -> None:
    transport = os.environ.get("MCC_TRANSPORT", "stdio").lower()
    if transport == "http":
        mcp.run(transport="http", host="127.0.0.1", port=int(os.environ.get("MCC_PORT", "8765")))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
