---
name: minecraft-asset-textures
description: Minecraft 像素资产与 cube 模型：16×16 方块贴图、物品图标、自发光 mask、.bbmodel 写入与校验。用户要求「画个方块贴图 / 做个物品图标 / 让它发光 / 做个模型」时使用。
---

# 像素资产与模型

## 一条铁律

工具的职责是**确定性处理**（尺寸、调色板、alpha、mask、结构校验）；"好不好看"由你看图判断。工具返回的是数字，不是分数——别把 `tileable_hint` 当成审美结论。

## 方块贴图（标准完整单方块）

- 尺寸默认 16×16；`block_texture(source, size=16, colors=16)`：最近邻缩放 + 中位切分调色板 + alpha 二值化。
- 调色板控制在 16 色以内，明暗差≥8 级，禁止抗锯齿、模糊、渐变。
- 六面语义：正面（`north`）承担方块身份；侧面可有细节，顶/底不要放"正面才有的标志"。
- 接缝：`seam.tileable_hint=false` 说明左右/上下不连续，要改边缘像素或直接说清楚"这块不需求平铺"。
- 状态（亮/灭、开/关）**共用一张基础贴图**：熄灭态=原图，点亮态=同一张图 + 自发光 mask 叠加，不要生成第二套完整贴图。

## 物品图标

- 默认 32×32（16 也可以）；`item_icon(source, size=32, remove_background=True, background_color="#RRGGBB", tolerance=0~12)`。
- 抠图必须先明确背景色；容差默认 0，调高等于接受相近像素一起消失。
- 报告 `content_bbox`：贴边或留白过大都要重做构图。
- 同一系列图标保持统一重心、统一光源方向。

## 自发光

```
emissive_mask(base="<成品16×16>", threshold=150, tint="#ffffff")
```

- 阈值是像素亮度（0.2126R+0.7152G+0.0722B），返回 `emissive_pixels` 与 `emissive_ratio`；比例过高（>0.35）说明整块都在发光，不是"局部发光"。
- mask 之外的所有像素必须与基础图逐像素一致——不要重画。

## 色板体检

`palette_report(path)`：`distinct_colors` 超过 24 就该怀疑是否走偏成照片风；`top` 里看主色是否与设计一致。

## cube 模型（.bbmodel）

spec 结构：

```json
{"name": "crate", "resolution": 16,
 "groups": [{"name": "body", "cubes": [
   {"name": "base", "from": [0,0,0], "to": [16,16,16]},
   {"name": "lid", "from": [0,16,0], "to": [16,18,16], "origin": [8,16,8], "rotation": [0,-10,0]}]}]}
```

- `from` 必须严格小于 `to`；`rotation` 每轴 ≤ ±90；UV 不越出 resolution。
- 块与块之间允许旋转，但不要靠"贴面重合"假装细节——重合面进游戏会闪烁。
- 写完必须 `bbmodel_validate(path)`，`ok=false` 就看 `issues` 逐条修。
- 生物/人物的头部按"一个 cube + 贴图表达五官"，别拆一堆小方块做脸。

## 交付前的自检清单

1. 不看文件名能认出是什么？
2. 在 16×16（方块）/ 32×32（图标）实际尺寸下仍可读？
3. alpha 是否只有 0/255，没有脏边？
4. 同一组资产的调色板与光照是否一致？
5. 有没有占位符、水印、裁切、空白带？
