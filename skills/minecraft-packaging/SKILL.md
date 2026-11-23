---
name: minecraft-packaging
description: Minecraft 打包与分发：资源包/材质包 zip、光影包结构、整合包 .mrpack。用户要「打个材质包 / 出个整盒 / 打包光影」时使用。
---

# 打包

## 资源包 / 材质包

结构：

```
my_pack/
  pack.mcmeta        ← 必须，pack_format 是整数
  pack.png           ← 可选 128×128 图标
  assets/<namespace>/textures/...
  assets/<namespace>/models/...
  assets/<namespace>/lang/zh_cn.json
```

- `resourcepack_build(pack_dir)` 会先校验 `pack.mcmeta`（必须有整数 `pack_format`）和 `assets/` 存在，再打成 zip。
- `pack_format` 对照：1.20.1→15，1.20.4→22，1.20.6→41，1.21.1→34，1.21.4→46，1.21.8→64。跨版本要按目标版本改，别沿用。
- 覆盖原版贴图时文件名必须等于原版 id（`textures/block/stone.png`）；换成别的命名空间要改模型/blockstate 引用。
- 打包后 zip 里 `pack.mcmeta` 必须在**根目录**，不是子目录。

## 光影包

```
shaders/shaders.properties
shaders/composite*.fsh/.vsh
shaders/final.fsh/.vsh
shaders/gbuffers_terrain.fsh/.vsh
```

本套件能校验结构和打包，**不能证明视觉效果**：真实光影要用户装 Iris/OptiFine 进游戏看。别用"打包成功"冒充"光影正确"。

## 整合包（.mrpack）

```
modpack_build(name="...", mc_version="1.21.1",
              mods=["sodium", {"slug": "lithium", "version_id": "<id>"}],
              overrides_dir="<可选 overrides>")
```

- 生成 zip + `modrinth.index.json`：`files[]` 每项含 `path`、`downloads[url]`、`hashes.sha1/sha512`、`fileSize`，由 Modrinth 现查，不手写。
- `dependencies` 写 `minecraft` 与 `fabric-loader`；**只支持 fabric**（Forge/NeoForge loader 版本矩阵未验证，别猜）。
- `.mrpack` 不是"装进现有实例"的东西：它是独立实例，交给启动器导入，或 `mc_launch` 当独立实例跑。
- 建包不需要 packwiz，也不需要预下载 jar。

## 交付检查

1. 报告里给出 zip 绝对路径、文件数、体积。
2. 资源包要说明 `pack_format` 与目标版本是否匹配。
3. 整合包要列出实际解析到的 mod 版本，以及是否含 fabric-api。
4. 任何"未进游戏验证"的部分要直说。
