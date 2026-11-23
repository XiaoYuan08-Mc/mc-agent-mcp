---
name: minecraft-mod-dev
description: 从零做 Minecraft Java mod（Fabric / NeoForge）：脚手架、写代码与资源、构建出 jar、装进实例。用户要求「做个模组 / 加个方块 / 加个物品 / 加个实体 / 改 mod」时使用。
---

# Java Mod 开发流程

## 1. 定目标（不要跳过）

- 版本 + loader 必须来自用户或已有实例（`mc_instance(action="list")`）。**不要**默认 1.21.1。
- 新建项目先列资产清单：玩家会看到什么（方块贴图 / 物品图标 / 实体模型 / GUI / 音效）。没有图标的物品进游戏就是紫黑格。

## 2. 脚手架

```
scaffold_mod(loader="fabric", mc_version="1.21.1", mod_id="my_mod", name="My Mod",
             dest="<项目目录>")
```

返回里重点看 `resolved`（loader / fabric_api / loom / java）与 `gradle_wrapper`：

- Fabric：`officialMojangMappings()`，不猜 yarn 版本；`fabric-api` 版本从 Modrinth 现查。
- NeoForge：`net.neoforged.moddev` + `neoForge { version = ... }`，版本从 neoforged maven 现查。
- **Forge 不做**：MDK 与 Gradle 矩阵未验证，猜版本等于交付坏工程。用户要 Forge 就说明限制。
- 生成的是 Gradle 8.10 wrapper（Loom 不能在 Gradle 9 上配置）。

## 3. 写内容

按 1.21.1 的注册习惯来（`Registry` / `Registries` 键、`identifier` 小写下划线、`blockstate` + `models/block` + `models/item` + `items/<id>.json` 客户端物品定义都要齐）。视版本不同以官方文档为准，别照搬旧版本 API。

- 方块：几何是完整 1×1×1 → 六面贴图 + blockstate/model；有凹洞/多部件 → 才做自定义模型。
- 物品：至少要 `assets/<ns>/textures/item/<id>.png` + `models/item/<id>.json`。
- 材质默认 16×16，透明像素用 alpha=0，别用半透明。

## 4. 构建

```
gradle_build(project_dir="<项目目录>", task="build", timeout=1800)
```

读回执三件事：`ok`、`artifacts`（`build/libs/*.jar`，忽略 `-sources`）、`output_tail`。首次构建会下载 Loom/MC/依赖，慢是正常的；失败要按 `log` 里的第一处真实报错改，不要盲改 build.gradle 版本号。

## 5. 装进实例并启动

```
mc_install(instance="...", artifact="<jar>")     # 覆盖会留 .bak
mc_runtime(instance="...", action="ensure")      # 先补运行时，不启动
mc_runtime(instance="...", action="launch")
mc_logs(instance="...", lines=120)               # 新日志里要有你的 mod 加载行
```

`mc_install` 只收 mod / 资源包 / 光影；`.mrpack` 不许塞进现有实例。

## 6. 验收口径

- "构建成功"只证明能编译；"启动无异常"要有日志证据；视觉/交互正确要用户进游戏确认，或你确实拿到了截图。
- 报错时先区分：版本不匹配 / 缺依赖（fabric-api、GeckoLib）/ 注册名冲突 / mixin 失败。四类改法完全不同。
