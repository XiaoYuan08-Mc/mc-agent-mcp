"""mc-agent 冒烟测试：真跑一遍 50 个工具的主链路。

不联网的部分全部执行；需要实例的部分只做参数校验与只读动作。
运行：在仓库根执行 python tests/smoke_mc_agent.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MCC_HOME", str(Path(tempfile.gettempdir()) / "mc-agent-test"))

from mc_agent import server as S  # noqa: E402


def call(tool, **kwargs):
    import inspect
    fn = getattr(S, tool)
    sig = inspect.signature(fn)
    allowed = {k: v for k, v in kwargs.items() if k in sig.parameters}
    dropped = set(kwargs) - set(allowed)
    try:
        out = fn(**allowed)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {exc}", "dropped": sorted(dropped)}
    if isinstance(out, dict) and dropped:
        out["__dropped__"] = sorted(dropped)
    return out


def show(label, payload, keys=("output", "preview", "ok", "issues", "error", "capability")):
    if isinstance(payload, dict):
        brief = {k: payload[k] for k in keys if k in payload}
        print(f"  {label}: {json.dumps(brief, ensure_ascii=False)[:220]}")
    else:
        print(f"  {label}: {str(payload)[:200]}")
    return payload


def main():
    ok, fail = 0, 0
    def check(label, payload):
        nonlocal ok, fail
        if isinstance(payload, dict) and payload.get("__error__"):
            print(f"  FAIL {label}: {payload['__error__']}")
            fail += 1
            return payload
        ok += 1
        show(label, payload)
        return payload

    print("== 0. 工具清单")
    async def _count():
        tools = await S.mcp.list_tools()
        return tools
    tools = asyncio.run(_count())
    print(f"  registered tools: {len(tools)}")

    print("== 1. 概念 → 模型 → 贴图 → 骨骼 → 动画 → 预览 → 导出")
    c = check("design_model_concepts", call("design_model_concepts", prompt="红宝石傀儡，方正机械感", kind="model"))
    cid = c["concepts"][0]["concept_id"]
    g = check("generate_3d_model", call("generate_3d_model", concept_id=cid, wants_animation=True, name="ruby_golem"))
    asset_id = g["asset_id"]
    check("texture_3d_model", call("texture_3d_model", style_prompt="rusty red", resolution=16,
                                   palette=["#b3352e", "#e26a5a", "#6e1f1a", "#f2c9a0"]))
    b = check("list_model_bones", call("list_model_bones"))
    bone_names = [x["name"] for x in b.get("bones", [])]
    print(f"    bones: {bone_names}")
    check("apply_animation", call("apply_animation", name="idle", length=2.0, loop="loop", bones=[
        {"bone": bone_names[0], "channel": "rotation", "time": 0, "vector": [0, 0, 0]},
        {"bone": bone_names[0], "channel": "rotation", "time": 1.0, "vector": [0, 6, 0]},
    ]))
    v = check("view_3d_model", call("view_3d_model", note="smoke"))
    check("export_asset(bbmodel)", call("export_asset", format="bbmodel", asset_name="ruby_golem"))
    check("export_asset(resourcepack)", call("export_asset", format="resourcepack", asset_name="ruby_golem", namespace="mcagent"))
    check("export_asset(glb)", call("export_asset", format="glb", asset_name="ruby_golem"))
    check("export_asset(geckolib)", call("export_asset", format="geckolib", asset_name="ruby_golem"))

    print("== 2. 绑骨五段")
    i = check("inspect_mesh_parts", call("inspect_mesh_parts", asset_id=asset_id))
    receipt = i["receipt"]
    parts = i["inventory"]
    labels = []
    for p in parts:
        labels.append({"part_id": p["part_id"], "role": p["part_id"], "motion_chain": "body",
                       "level": 0, "side": "center", "confidence": 0.9})
    check("label_mesh_parts", call("label_mesh_parts", inspection_receipt=receipt, parts=labels, finalize=True))
    groups = [{"name": "all", "members": [p["part_id"] for p in parts]}]
    check("group_mesh_parts", call("group_mesh_parts", inspection_receipt=receipt, groups=groups))
    check("plan_group_motion", call("plan_group_motion", inspection_receipt=receipt, groups=[
        {"group": "all", "kind": "rigid", "motion_chain": "body"}]))
    check("apply_rig", call("apply_rig", inspection_receipt=receipt))

    print("== 3. 方块纹理 → 自发光 → 发布")
    bt = check("generate_standard_block_texture", call(
        "generate_standard_block_texture", project_dir=str(ROOT / "mc-home" / "projects" / "smoke_rp"),
        namespace="mcagent", block_id="ruby_block", material_prompt="crystal 红宝石 晶体",
        resolution=16, overwrite=True))
    check("generate_block_emissive_mask", call("generate_block_emissive_mask", staging_metadata=bt))
    em = check("generate_block_emissive_mask", call("generate_block_emissive_mask", staging_metadata=bt))
    check("generate_block_emissive_overlay", call("generate_block_emissive_overlay",
                                                 mask_manifest=em, state_change="lit"))
    check("publish_standard_block_asset", call("publish_standard_block_asset", staging_metadata=bt))

    print("== 4. 图标 / 物品注册 / 面板 / 布局")
    check("generate_item_icon", call("generate_item_icon", size=32))
    check("render_inventory", call("render_inventory", size=64))
    proj = str(ROOT / "mc-home" / "projects" / "smoke_mod")
    check("register_java_items(dry)", call("register_java_items", dest_path=proj, namespace="mcagent",
                                           items=[{"id": "ruby", "name": "红宝石", "stack_size": 64}],
                                           action="preview"))
    check("java_panel_pipeline", call("java_panel_pipeline", panel_id="crate", project_dir=proj,
                                      title="Crate", slot_groups=[{"id": "main", "x": 8, "y": 18, "cols": 9, "rows": 3}]))
    check("bedrock_panel_pipeline", call("bedrock_panel_pipeline", panel_id="crate", project_dir=proj))
    lay = check("ui_layout", call("ui_layout", action="write", layout_id="crate_ui", name="Crate UI",
                                  elements=[{"id": "title", "type": "label", "x": 8, "y": 6, "w": 100, "h": 10},
                                            {"id": "grid", "type": "panel", "x": 8, "y": 18, "w": 162, "h": 54}],
                                  constraints=[{"kind": "non_overlapping", "elements": ["title", "grid"]}]))
    check("ui_asset_set", call("ui_asset_set", action="write", name="crate assets", layout_id="crate_ui",
                               assets=[{"id": "icon_ruby", "kind": "texture", "path": "x.png"}]))

    print("== 5. 文档 / 技能 / 状态")
    check("mc_api_docs", call("mc_api_docs", topic="blockentity"))
    check("mc_api_search", call("mc_api_search", query="item register", physical_side="common"))
    check("activate_skill", call("activate_skill", skill_id="minecraft-asset-textures"))
    check("asset_roster", call("asset_roster", needed=["ruby_block"], not_needed=["shader"]))
    check("validation_plan", call("validation_plan", scope="smoke", required_gates=["build"]))
    check("project_brief", call("project_brief", action="set", brief_summary="smoke"))
    check("attach_reference", call("attach_reference", attachment_id="ref1", visual_summary="red gem"))

    print("== 6. 云端边界（只剩发布/社区/搜索三类）")
    for name, kwargs in (
        ("publish_to_community", {"artifact_path": "x.zip"}),
        ("community_browse", {"query": "shader"}),
        ("community_fetch", {"post_id": "abc"}),
        ("web_search", {"query": "fabric api"}),
    ):
        r = call(name, **kwargs)
        if r.get("error") == "capability_unavailable":
            ok += 1
            print(f"  OK   {name}: capability_unavailable")
        else:
            fail += 1
            print(f"  FAIL {name}: 未按边界返回 -> {str(r)[:120]}")

    print("== 7. 生成式图像（只探后端，不真出图以免触发 45s 限速）")
    from mc_agent import imagegen
    prov = imagegen.providers()
    ready = [k for k, v in prov.items() if v["ready"]]
    print(f"  providers ready: {ready}")
    if "pollinations" in ready:
        ok += 1
    else:
        fail += 1
        print("  FAIL pollinations 不可用")

    print("== 8. 三角网格 → 立方体（真拟合）")
    glb = ROOT / "mc-home" / "exports" / "ruby_golem.glb"
    if glb.exists():
        mesh = check("convert_to_cubes(glb)", call("convert_to_cubes", mesh_path=str(glb), resolution=24))
        if mesh.get("boxes", 0) > 0:
            ok += 1
            print(f"    voxels={mesh.get('voxels')} boxes={mesh.get('boxes')} grid={mesh.get('grid')}")
        else:
            fail += 1
    else:
        print("  SKIP（没有 ruby_golem.glb，先跑第 1 节）")

    print("== 9. Win32 注入链路（枚举窗口 / 焦点 / 按键结构）")
    from mc_agent import wininput
    wins = wininput.windows()
    print(f"  visible windows: {len(wins)}")
    if len(wins) >= 1:
        ok += 1
        tgt = wins[0]
        shot = None
        try:
            shot = wininput.screenshot_window(tgt["hwnd"], str(ROOT / "mc-home" / "exports" / "_smoke_win.png"),
                                             focus_first=False, prefer="printwindow")
            print(f"    screenshot: {shot['method']} uniform={shot['uniform_frame']} size={shot['size']}")
        except Exception as exc:  # noqa: BLE001
            print(f"    screenshot skipped: {exc}")
        mc = wininput.find_minecraft() if any(w["minecraft"] for w in wins) else None
        print(f"    minecraft window: {mc['title'] if mc else '未运行'}")
    else:
        fail += 1
        print("  FAIL 枚举不到窗口")

    print("== 10. 实例只读")
    check("mc_instance(list)", call("mc_instance", action="list"))
    check("modpack(search)", call("modpack", action="search", mc_version="1.21.1", query="sodium"))

    print(f"\n结果：ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
