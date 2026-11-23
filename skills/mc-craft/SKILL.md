---
name: mc-craft
description: Minecraft 创造/开发总入口。用户要做 Minecraft mod、资源包、光影、整合包、方块贴图、或要装/启动测试实例时先用这个技能判断路线，再按需加载子技能；涉及「我的世界 / MC / 模组 / 材质包 / 整合包」等词时优先触发。
---

# mc-craft 总路由

本地 MCP server `mc-craft` 提供 16 个工具，覆盖"实例运行 / 工程构建 / 打包 / 像素资产 / 模型数据"。**云端生成类能力（文生 3D、AI 画贴图、社区发布）不在本套件里**，遇到这类需求直接说明缺口，不要假装能做。

## 第一步永远是确认目标

1. 问清（或从上下文取）：**版本**（如 1.21.1）、**loader**（fabric/neoforge/vanilla）、**要交付什么**（可编译 jar / 资源包 zip / 整合包 / 只是贴图）。
2. `mc_instance(action="list")` 看已有实例；没有就用 `mc_instance(action="create", ...)` 建一个。版本和 loader 是后面一切构建的硬约束。
3. 版本号一律**现查**：Fabric loader / Fabric API / Loom / NeoForge 由 `scaffold_mod` 在生成时解析。任何"大概 0.16.x"的猜测都会让用户那边装不上。

## 路线表

| 用户想要 | 加载技能 | 核心工具 |
| --- | --- | --- |
| 能玩的 mod（方块/物品/实体/逻辑） | `minecraft-mod-dev` | `scaffold_mod` → `gradle_build` → `mc_install` → `mc_runtime` |
| 只换贴图/模型/音效 | `minecraft-packaging` | `resourcepack_build` |
| 光影包 | `minecraft-packaging` | `resourcepack_build`（结构校验）+ 明确说明无法本地验证视觉效果 |
| 一组 mod 的整合包 | `minecraft-packaging` | `modpack_build` |
| 方块/物品的像素图 | `minecraft-asset-textures` | `block_texture` / `item_icon` / `emissive_mask` / `palette_report` |
| 要进游戏确认效果 | `minecraft-runtime-check` | `mc_runtime(ensure/launch)` + `mc_logs` |
| 自建 cube 模型 | `minecraft-asset-textures` | `bbmodel_write` / `bbmodel_validate` |

## 纪律

- 只做用户要的：贴图需求不顺手 scaffold 工程；构建成功不等于进游戏验证成功；本地成功不等于发布。
- 每个"完成"结论都要有回执：`gradle_build` 的 `artifacts`、`mc_install` 的 `sha256`、`mc_logs` 的新日志行。没有证据就说"未验证"。
- 覆盖安装会留 `.bak`，仍要提醒用户。
- 1.20.5+ 需要 JDK 21，1.20.x 用 JDK 17；`gradle_build` 会自动选，选错会直接报错而不是硬编。
- 基岩版 Add-On 本套件**不支持**：只能开发打包后交给用户自己开游戏。
