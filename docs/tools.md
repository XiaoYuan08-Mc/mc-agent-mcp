# 工具清单

本文件由 `scripts/gen_tools_doc.py` 从运行中的 server 自动生成，共 **51 个工具**。

## 总览

| 工具 | 说明 | 必填参数 |
| --- | --- | --- |
| `activate_skill` | 激活工作流技能（读仓库 skills/ 下的 SKILL.md）：工作流、纪律、验收清单都在里面 | skill_id |
| `apply_animation` | 把关键帧写进当前模型 | name |
| `apply_rig` | 把语义表聚成骨骼树并写回模型（pivot 来自 part 几何） | inspection_receipt |
| `asset_roster` | 资产台账：这一轮需要哪些资产、哪些明确不做、哪些要运行时验证 | — |
| `attach_reference` | 登记一个参考附件（图片/工程），写进会话状态，后续按 id 引用 | attachment_id |
| `bedrock_panel_pipeline` | 生成基岩 JSON-UI 面板（ui/<id>.json），控件按网格自动排布 | — |
| `community_browse` | 浏览社区四库 | — |
| `community_fetch` | 下载社区产物 | post_id |
| `convert_to_cubes` | 三角网格 → 立方体（真拟合）：GLB/OBJ → 体素化 → 贪心合并 → .bbmodel | — |
| `design_model_concepts` | 模型创建第 1 步：给 4 个概念方案（几何契约 + 缩略图），让用户挑一个 | prompt |
| `export_asset` | 导出当前模型 | — |
| `generate_3d_model` | 模型创建第 2 步：概念 → cube 模型（默认本地参数化 | concept_id |
| `generate_block_emissive_mask` | 从方块贴图提自发光 mask：按亮度阈值（或 regions 指定矩形）挑像素，出灰度图 + manifest | staging_metadata |
| `generate_block_emissive_overlay` | 按 mask 生成点亮态 overlay（mask 区域重新上色 + 提亮），并写 manifest | mask_manifest |
| `generate_image` | 生成式绘图：多后端适配（pollinations 免费 / openai / sdwebui / comfyui） | prompt |
| `generate_item_icon` | 32px 物品图标：从当前模型渲染或读图片，抠背景 + 内容包围盒 + 调色板量化 | — |
| `generate_standard_block_texture` | 标准方块贴图：材质关键词 → 程序化像素图 + blockstate/model/item model 全套 | — |
| `gradle_build` | 跑 Gradle | — |
| `group_mesh_parts` | 把已标注的 part 聚成语义组（core/head/front_left_leg/…），一键覆盖全部 part | inspection_receipt, groups |
| `import_asset` | 导入资产 | path |
| `inspect_mesh_parts` | 分件：给出 part 清单（包围盒/质心/三角面数）+ 高亮图 + inspection_receipt | — |
| `item_visual_pipeline` | 物品视觉编排：分类 → 尺寸校验 → 出图标（或投影）→ 落进资源包目录 | — |
| `java_panel_pipeline` | 生成 Java Screen 骨架：槽位按 176 宽画布计算，重叠/越界会在 issues 里点名 | — |
| `label_mesh_parts` | 写语义：每个 part 给 role / motion_chain / level / side / attachment / 置信度 | inspection_receipt, parts |
| `list_model_bones` | 列出当前模型骨骼（名字 / 父级 / pivot / 立方体数） | — |
| `mc_api_docs` | 查 MC API 文档（离线语料，标注 since）：Item/Block/BlockEntity/网络/渲染/资源包/配方/GeckoLib | — |
| `mc_api_search` | 检索 API 语料，按符号名加权排序 | query |
| `mc_capture` | 取帧 | — |
| `mc_dev_run` | 开发态运行：start 在工程目录后台跑 gradlew runClient | — |
| `mc_game_test` | 游戏内注入：键盘 / 鼠标 / 文本，走 Win32 SendInput（不需要装 mod） | — |
| `mc_install` | 把 jar / 资源包 / 光影装进实例（同名文件留 .bak） | artifact_path |
| `mc_instance` | 实例管理：list / create / locate / inspect | — |
| `mc_launch` | 启动 / 停止 / 查看实例 | — |
| `mc_live_update` | 热重载落地：把产物或改动拷进实例（mod→mods，资源→resourcepacks） | — |
| `mc_logs` | 读实例日志尾部 | — |
| `mc_runtime_prepare` | 只装不发：下载并补齐版本/加载器/资源索引 | — |
| `mc_visual_verdict` | 记录一次视觉判读（截图 id + 结论 + 观察），落进会话状态供后续引用 | — |
| `modpack` | 整合包：action=search 查 Modrinth | — |
| `plan_group_motion` | 逐组裁运动：kind=rigid\|articulated\|attachment\|eye\|static | inspection_receipt, groups |
| `project_brief` | 项目协作记录：目标、范围、参考、最少资产数、交付物、运行时检查项 | — |
| `publish_standard_block_asset` | 把上一次生成的 staging 记录发布到项目目录，并核对文件是否齐全 | staging_metadata |
| `publish_to_community` | 发布到社区市场 | artifact_path |
| `register_java_items` | 生成 Java 物品注册（Fabric: Registry.register / NeoForge: DeferredRegister）+ 模型 + 语言文件 | — |
| `render_inventory` | 把当前模型渲染成 64×64 背包位图（最近邻，像素风） | — |
| `scaffold_mod` | 生成可编译的 Fabric / NeoForge 工程（loader/Loom/Gradle 版本现查） | mod_id |
| `texture_3d_model` | 模型创建第 3 步：给当前模型上贴图（程序化调色板像素图，16×N 色带） | — |
| `ui_asset_set` | 资产集登记：把图标/九宫格/贴图绑到某个布局上，校验布局存在 | — |
| `ui_layout` | 布局 DSL：元素盒模型 + 越界/重叠/约束校验 + PNG 预览 | — |
| `validation_plan` | 本轮验收计划：范围、必须过的闸门、交付物、通过标准、什么情况停手 | — |
| `view_3d_model` | 把当前模型渲染成等距预览图（离线软光栅，能看清造型与配色） | — |
| `web_search` | 联网搜索 | query |

## 逐个工具

### `activate_skill`

激活工作流技能（读仓库 skills/ 下的 SKILL.md）：工作流、纪律、验收清单都在里面。

resource 可指定 references/ 下的文件；不传则列出可用 references。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `skill_id` | string | 是 | — | — |
| `resource` | string | 否 | — | — |
| `reason` | string | 否 | — | — |

### `apply_animation`

把关键帧写进当前模型。旋转单位是度，位移单位是方块。

bones 每项：{bone, channel: rotation|position|scale, time, vector:[x,y,z]}
整模竖直位移会被钳到 0（下去穿地、上去像漂浮）。骨骼名错了直接拒，不生成空动画。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | string | 是 | — | — |
| `length` | number | 否 | 1.0 | — |
| `loop` | string | 否 | loop | — |
| `bones` | array / null | 否 | None | — |

### `apply_rig`

把语义表聚成骨骼树并写回模型（pivot 来自 part 几何）。

正常路径留空 bones：按 motion_chain + level 自动聚类。手写 bones 只作为
特殊机械结构的显式覆盖，返回里会标 manual_override。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `inspection_receipt` | object | 是 | — | — |
| `bones` | array / null | 否 | None | — |
| `splits` | array / null | 否 | None | — |
| `drop` | array / null | 否 | None | — |
| `keep_emissive_eyes` | boolean | 否 | True | — |

### `asset_roster`

资产台账：这一轮需要哪些资产、哪些明确不做、哪些要运行时验证。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `needed` | array / null | 否 | None | — |
| `not_needed` | array / null | 否 | None | — |
| `runtime_behaviours` | array / null | 否 | None | — |
| `no_runtime_behaviour` | array / null | 否 | None | — |

### `attach_reference`

登记一个参考附件（图片/工程），写进会话状态，后续按 id 引用。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `attachment_id` | string | 是 | — | — |
| `scope` | string | 否 | project | — |
| `reference_role` | string | 否 | style | — |
| `visual_summary` | string | 否 | — | — |
| `observed_subject_count` | integer | 否 | 0 | — |
| `subject_inventory` | array / null | 否 | None | — |
| `project_scope` | string | 否 | — | — |
| `intended_use` | string | 否 | — | — |
| `user_directive` | string | 否 | — | — |

### `bedrock_panel_pipeline`

生成基岩 JSON-UI 面板（ui/<id>.json），控件按网格自动排布。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | write | — |
| `panel_id` | string | 否 | — | — |
| `project_dir` | string | 否 | — | — |
| `panel_mode` | string | 否 | screen | — |
| `api_mode` | string | 否 | json_ui | — |
| `title` | string | 否 | — | — |
| `controls` | array / null | 否 | None | — |
| `canvas_width` | integer | 否 | 320 | — |
| `canvas_height` | integer | 否 | 180 | — |
| `grid_columns` | integer | 否 | 3 | — |
| `grid_rows` | integer | 否 | 2 | — |
| `binding_target` | string | 否 | — | — |

### `community_browse`

浏览社区四库。本实现不接入社区服务；替代是 Modrinth 检索。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 否 | — | — |
| `content_type` | string | 否 | mod | — |
| `sort` | string | 否 | relevance | — |
| `limit` | integer | 否 | 20 | — |
| `post_id` | string | 否 | — | — |

### `community_fetch`

下载社区产物。产物托管在远端，本实现无下载凭据。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `post_id` | string | 是 | — | — |
| `what` | string | 否 | all | — |
| `dest_dir` | string | 否 | — | — |

### `convert_to_cubes`

三角网格 → 立方体（真拟合）：GLB/OBJ → 体素化 → 贪心合并 → .bbmodel。

resolution 控制台阶精度（16 粗 / 32 默认 / 64 细，超过 64 会很慢）。
solid=true 会把表面体素填成实心（封闭体积，代价是盒子数暴涨）。
当前资产已经是 .bbmodel 时，退化为"轴对齐校验"，不改几何。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `mesh_path` | string | 否 | — | — |
| `resolution` | integer | 否 | 32 | — |
| `solid` | boolean | 否 | False | — |
| `target_pixels` | number | 否 | 16.0 | — |
| `out_path` | string | 否 | — | — |

### `design_model_concepts`

模型创建第 1 步：给 4 个概念方案（几何契约 + 缩略图），让用户挑一个。

不依赖图像服务，直接给 4 组可读参数
（体型/腿长/头身比/调色板/造型说明）+ 等距渲染缩略图。挑中的 concept_id
就是 generate_3d_model 的几何契约。永远不要让 agent 替用户挑。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `prompt` | string | 是 | — | — |
| `kind` | string | 否 | model | — |

### `export_asset`

导出当前模型。format: bbmodel | resourcepack | geckolib | glb | mcaddon(受限)。

- bbmodel：Blockbench 工程文件（可继续手改）
- resourcepack：Java 资源包 zip（含模型 + 贴图 + 物品模型）；pack.mcmeta 按
  mc_version 生成（1.21.9+ 写 min_format/max_format，26.3 = 97）
- geckolib：geo/animations/texture 三件套，直接放 mod 的 assets 目录
- glb：最小 glTF 2.0 二进制（顶点色，无贴图）
- mcaddon：只产 geometry + 贴图，行为包/刷怪蛋需自行补（本地不生成实体行为）

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_name` | string | 否 | — | — |
| `format` | string | 否 | bbmodel | — |
| `entity_base` | string | 否 | — | — |
| `dest_path` | string | 否 | — | — |
| `namespace` | string | 否 | mcagent | — |
| `emissive_part_ids` | array / null | 否 | None | — |
| `pixel_grain` | integer | 否 | 16 | — |
| `mc_version` | string | 否 | 1.21.1 | — |

### `generate_3d_model`

模型创建第 2 步：概念 → cube 模型（默认本地参数化；provider=meshy 走真 image-to-3d）。

local：概念参数展开成 cube 树，骨骼分组/UV 一次给全，立即可绑骨。
meshy：把 image（或 concept 的缩略图）丢给 Meshy 出三角网格，再自动跑
  convert_to_cubes 体素化成立方体。需要 MESHY_API_KEY，且要等 1–5 分钟。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `concept_id` | string | 是 | — | — |
| `wants_animation` | boolean | 否 | True | — |
| `name` | string | 否 | — | — |
| `output` | string | 否 | — | — |
| `provider` | string | 否 | local | — |
| `image` | string | 否 | — | — |
| `resolution` | integer | 否 | 32 | — |
| `polycount` | integer | 否 | 1000 | — |

### `generate_block_emissive_mask`

从方块贴图提自发光 mask：按亮度阈值（或 regions 指定矩形）挑像素，出灰度图 + manifest。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `staging_metadata` | object / string | 是 | — | — |
| `emissive_mode` | string | 否 | threshold | — |
| `activation` | string | 否 | always | — |
| `world_light_level` | integer | 否 | 0 | — |
| `regions` | array / null | 否 | None | — |
| `intensity_mode` | string | 否 | binary | — |
| `decision_reason` | string | 否 | — | — |
| `threshold` | integer | 否 | 165 | — |

### `generate_block_emissive_overlay`

按 mask 生成点亮态 overlay（mask 区域重新上色 + 提亮），并写 manifest。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `mask_manifest` | object / string | 是 | — | — |
| `state_change` | string | 否 | — | — |
| `face_edits` | array / null | 否 | None | — |
| `detail_density` | string | 否 | — | — |
| `nano_model` | string | 否 | — | — |
| `glow_color` | array / null | 否 | None | — |

### `generate_image`

生成式绘图：多后端适配（pollinations 免费 / openai / sdwebui / comfyui）。

provider=auto 时按 OPENAI_API_KEY → 本地 SD WebUI → 本地 ComfyUI → pollinations 顺序探测。
pollinations 无需 key，但每 IP 45 秒 1 张（设 POLLINATIONS_TOKEN 解除）。
target_pixel_size>0 会按最近邻缩到该边长，直接能当像素资产用。
返回里带真实 provider 与落盘路径——拿去喂 generate_item_icon / 方块贴图后处理。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `prompt` | string | 是 | — | — |
| `dest_path` | string | 否 | — | — |
| `aspect_ratio` | string | 否 | 1:1 | — |
| `reference_images` | array / null | 否 | None | — |
| `reference_roles` | array / null | 否 | None | — |
| `artifact_role` | string | 否 | — | — |
| `require_bound_reference` | boolean | 否 | False | — |
| `pixel_style` | boolean | 否 | True | — |
| `target_pixel_size` | integer | 否 | 0 | — |
| `isolation_mode` | string | 否 | — | — |
| `matte_color` | string | 否 | — | — |
| `variant_key` | string | 否 | — | — |
| `ui_stage` | string | 否 | — | — |
| `ui_layout_id` | string | 否 | — | — |
| `ui_target_id` | string | 否 | — | — |
| `ui_style_reference` | string | 否 | — | — |
| `provider` | string | 否 | auto | — |
| `width` | integer | 否 | 0 | — |
| `height` | integer | 否 | 0 | — |
| `seed` | integer | 否 | 0 | — |
| `negative` | string | 否 | — | — |

### `generate_item_icon`

32px 物品图标：从当前模型渲染或读图片，抠背景 + 内容包围盒 + 调色板量化。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 否 | — | — |
| `background_color` | string | 否 | — | — |
| `background_tolerance` | integer | 否 | 10 | — |
| `design_prompt` | string | 否 | — | — |
| `overwrite` | boolean | 否 | False | — |
| `expected_existing_sha256` | string | 否 | — | — |
| `size` | integer | 否 | 32 | — |
| `source_path` | string | 否 | — | — |
| `output` | string | 否 | — | — |

### `generate_standard_block_texture`

标准方块贴图：材质关键词 → 程序化像素图 + blockstate/model/item model 全套。

材质识别：石/土/草/木/木板/金属/玻璃/砖/沙/晶体/羊毛/黑曜石。
face_layout=all 出单图，top_side_bottom 出三图。产物落地即可进资源包。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `project_dir` | string | 否 | — | — |
| `namespace` | string | 否 | mcagent | — |
| `block_id` | string | 否 | — | — |
| `material_prompt` | string | 否 | — | — |
| `resolution` | integer | 否 | 16 | — |
| `face_layout` | string | 否 | all | — |
| `palette` | array / null | 否 | None | — |
| `stateful_emissive_candidate` | boolean | 否 | False | — |
| `canonical_state` | string | 否 | — | — |
| `overwrite` | boolean | 否 | False | — |
| `dest_path` | string | 否 | — | — |

### `gradle_build`

跑 Gradle。mode=build|clean|run|test。自动按 MC 版本挑 JDK（1.20.x→17，1.21.x→21）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | string | 否 | build | — |
| `project_dir` | string | 否 | — | — |
| `timeout_s` | integer | 否 | 900 | — |

### `group_mesh_parts`

把已标注的 part 聚成语义组（core/head/front_left_leg/…），一键覆盖全部 part。

一个 part 只能进一个组；漏掉或多出都会拒。这里不裁运动。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `inspection_receipt` | object | 是 | — | — |
| `groups` | array | 是 | — | — |
| `asymmetric_part_ids` | array / null | 否 | None | — |
| `asymmetry_reason` | string | 否 | — | — |

### `import_asset`

导入资产。.bbmodel 直接当当前模型；.glb/.obj + convert_mesh=true 走体素化转方块。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | string | 是 | — | — |
| `asset_id` | string | 否 | — | — |
| `convert_mesh` | boolean | 否 | False | — |
| `resolution` | integer | 否 | 32 | — |

### `inspect_mesh_parts`

分件：给出 part 清单（包围盒/质心/三角面数）+ 高亮图 + inspection_receipt。

按 outliner 分组切分三角网格，并出双视角高亮图
（cube 模型的自然分件），语义判断留给调用方。receipt 里带几何哈希，
几何一改就失效，防止 part_id 指错东西。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 否 | — | — |
| `part_ids` | array / null | 否 | None | — |
| `motion_chain` | string | 否 | — | — |
| `include_related` | boolean | 否 | False | — |

### `item_visual_pipeline`

物品视觉编排：分类 → 尺寸校验 → 出图标（或投影）→ 落进资源包目录。

action=plan 只出计划；action=build 真的产图标/模型文件。平板图标优先用
generate_item_icon；模型投影只在 allow_model_projection_fallback=true 时做。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | plan | — |
| `asset_id` | string | 否 | — | — |
| `category` | string | 否 | item | — |
| `dimensions_blocks` | array / null | 否 | None | — |
| `inventory_policy` | string | 否 | auto | — |
| `forward_axis` | string | 否 | north | — |
| `has_dedicated_hand_model` | boolean | 否 | False | — |
| `texture_resolution` | integer | 否 | 32 | — |
| `source_icon_path` | string | 否 | — | — |
| `allow_model_projection_fallback` | boolean | 否 | False | — |
| `projection_fallback_reason` | string | 否 | — | — |
| `dest_path` | string | 否 | — | — |
| `namespace` | string | 否 | mcagent | — |
| `bedrock_format_version` | string | 否 | 1.20.0 | — |
| `notes` | string | 否 | — | — |
| `visual_source` | string | 否 | model | — |

### `java_panel_pipeline`

生成 Java Screen 骨架：槽位按 176 宽画布计算，重叠/越界会在 issues 里点名。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | write | — |
| `panel_id` | string | 否 | — | — |
| `project_dir` | string | 否 | — | — |
| `panel_kind` | string | 否 | simple | — |
| `title` | string | 否 | — | — |
| `slot_groups` | array / null | 否 | None | — |
| `widgets` | array / null | 否 | None | — |
| `include_player_inventory` | boolean | 否 | False | — |
| `canvas_width` | integer | 否 | 176 | — |
| `namespace` | string | 否 | — | — |
| `java_package` | string | 否 | — | — |

### `label_mesh_parts`

写语义：每个 part 给 role / motion_chain / level / side / attachment / 置信度。

receipt 必须是本次几何的；未检查过、缺失、多余的 id 都会拒。
所有 part 都有 draft 后才允许 finalize=true。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `inspection_receipt` | object | 是 | — | — |
| `parts` | array | 是 | — | — |
| `finalize` | boolean | 否 | False | — |

### `list_model_bones`

列出当前模型骨骼（名字 / 父级 / pivot / 立方体数）。写关键帧前必须先看。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 否 | — | — |

### `mc_api_docs`

查 MC API 文档（离线语料，标注 since）：Item/Block/BlockEntity/网络/渲染/资源包/配方/GeckoLib。

给 symbols 精确查，给 topic 模糊查；project_dir 存在时报告工程形态。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `topic` | string | 否 | — | — |
| `symbols` | array / null | 否 | None | — |
| `project_dir` | string | 否 | — | — |

### `mc_api_search`

检索 API 语料，按符号名加权排序；physical_side=client|server|both 过滤物理侧。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | — | — |
| `physical_side` | string | 否 | both | — |
| `project_dir` | string | 否 | — | — |
| `symbols` | array / null | 否 | None | — |
| `max_results` | integer | 否 | 8 | — |

### `mc_capture`

取帧。method=ingame 发 F2 让游戏自己存图；window 用 GDI 抓窗口；auto 先试游戏内。

游戏内置截图最可靠（读的是真实 GL 帧缓冲）；GDI 抓屏在窗口被遮挡或独占全屏时会得到纯色，
返回里 uniform_frame=true 就是这种情况。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `caption` | string | 否 | — | — |
| `allow_foreground` | boolean | 否 | False | — |
| `instance` | string | 否 | — | — |
| `method` | string | 否 | auto | — |
| `out_path` | string | 否 | — | — |

### `mc_dev_run`

开发态运行：start 在工程目录后台跑 gradlew runClient；status/stop 走 pid 文件。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | start | — |
| `project_dir` | string | 否 | — | — |

### `mc_game_test`

游戏内注入：键盘 / 鼠标 / 文本，走 Win32 SendInput（不需要装 mod）。

action: status | focus | key | hold | text | click | move | scroll
- key：点一次按键（duration_ms 为按住时长），modifier 支持 "shift+ctrl"
- hold：长按（duration_ms，默认 300）
- text：逐字 unicode 输入（聊天、命令）
- click：鼠标键，x 当点击次数，button=left/right/middle
- move：相对移动 x/y 像素（yaw_delta/pitch_delta 会叠加进来转视角）
- scroll：滚轮，y=格数（正=上）
窗口必须在前台；工具会自动抢焦点，抢不到会在 warning 里说。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | status | — |
| `control_id` | string | 否 | — | — |
| `x` | integer | 否 | 0 | — |
| `y` | integer | 否 | 0 | — |
| `key` | string | 否 | — | — |
| `modifier` | string | 否 | — | — |
| `duration_ms` | integer | 否 | 0 | — |
| `button` | string | 否 | — | — |
| `text` | string | 否 | — | — |
| `yaw_delta` | number | 否 | 0.0 | — |
| `pitch_delta` | number | 否 | 0.0 | — |
| `scroll_delta` | integer | 否 | 0 | — |
| `allow_foreground` | boolean | 否 | False | — |
| `instance` | string | 否 | — | — |
| `hwnd` | integer | 否 | 0 | — |

### `mc_install`

把 jar / 资源包 / 光影装进实例（同名文件留 .bak）。装 mod 前建议先 prepare。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `artifact_path` | string | 是 | — | — |
| `target` | string | 否 | — | — |
| `instance` | string | 否 | — | — |
| `minecraft_version` | string | 否 | — | — |
| `loader` | string | 否 | — | — |
| `install_dependencies` | boolean | 否 | False | — |
| `use_bmclapi` | boolean | 否 | True | — |
| `prepare_timeout_seconds` | integer | 否 | 900 | — |

### `mc_instance`

实例管理：list / create / locate / inspect。

create 需要 name + mc_version（loader 可选 vanilla/fabric/neoforge/quilt）；
locate 不传 name 时返回最近创建的实例；inspect 给目录、已装内容、进程状态。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | list | — |
| `name` | string | 否 | — | — |
| `mc_version` | string | 否 | — | — |
| `loader` | string | 否 | vanilla | — |
| `loader_version` | string | 否 | — | — |
| `notes` | string | 否 | — | — |

### `mc_launch`

启动 / 停止 / 查看实例。start 会后台起进程并写 launcher 日志。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `version` | string | 否 | — | — |
| `watch_seconds` | integer | 否 | 0 | — |
| `action` | string | 否 | start | — |
| `instance` | string | 否 | — | — |
| `use_bmclapi` | boolean | 否 | True | — |

### `mc_live_update`

热重载落地：把产物或改动拷进实例（mod→mods，资源→resourcepacks）。

热重载采用文件级更新 + 提示重启，不做进程内替换。
action=plan 只算要动哪些文件。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | apply | — |
| `project_dir` | string | 否 | — | — |
| `changed_paths` | array / null | 否 | None | — |
| `instance` | string | 否 | — | — |
| `artifact_path` | string | 否 | — | — |
| `expected_plan_id` | string | 否 | — | — |
| `dynamic_paths` | array / null | 否 | None | — |
| `content_log_path` | string | 否 | — | — |

### `mc_logs`

读实例日志尾部。log=latest 取最新启动日志，install 取安装日志。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `log` | string | 否 | latest | — |
| `tail` | integer | 否 | 80 | — |
| `instance` | string | 否 | — | — |

### `mc_runtime_prepare`

只装不发：下载并补齐版本/加载器/资源索引。首次启动前必须先跑这一条。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `instance` | string | 否 | — | — |
| `use_bmclapi` | boolean | 否 | True | — |
| `timeout_seconds` | integer | 否 | 900 | — |

### `mc_visual_verdict`

记录一次视觉判读（截图 id + 结论 + 观察），落进会话状态供后续引用。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `screenshot_id` | string | 否 | — | — |
| `verdict` | string | 否 | unknown | — |
| `checks` | array / null | 否 | None | — |
| `observations` | array / null | 否 | None | — |
| `viewpoint` | string | 否 | — | — |
| `next_action` | string | 否 | — | — |
| `blocker_code` | string | 否 | — | — |

### `modpack`

整合包：action=search 查 Modrinth；action=build 写 .mrpack（只支持 fabric loader）。

build 的 mods 可以是 Modrinth slug，也可以是 {slug|version_id}；依赖会一起解析。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | search | — |
| `mc_version` | string | 否 | — | — |
| `loader` | string | 否 | fabric | — |
| `query` | string | 否 | performance | — |
| `limit` | integer | 否 | 10 | — |
| `name` | string | 否 | — | — |
| `version_id` | string | 否 | — | — |
| `pack_summary` | string | 否 | — | — |
| `mods` | array / null | 否 | None | — |
| `include_dependencies` | boolean | 否 | True | — |
| `dest_path` | string | 否 | — | — |

### `plan_group_motion`

逐组裁运动：kind=rigid|articulated|attachment|eye|static。

articulated 每个成员都要 level；其它 kind 不许带 levels；attachment 必须给 attach_to。
kind=unknown 直接拒——回去重新 inspect。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `inspection_receipt` | object | 是 | — | — |
| `groups` | array | 是 | — | — |

### `project_brief`

项目协作记录：目标、范围、参考、最少资产数、交付物、运行时检查项。action=set|read。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | set | — |
| `brief_summary` | string | 否 | — | — |
| `project_scope` | string | 否 | — | — |
| `reference_ids` | array / null | 否 | None | — |
| `minimum_asset_count` | integer | 否 | 0 | — |
| `visual_asset_ids` | array / null | 否 | None | — |
| `visual_mode` | string | 否 | — | — |
| `deliverables` | array / null | 否 | None | — |
| `runtime_checks` | array / null | 否 | None | — |

### `publish_standard_block_asset`

把上一次生成的 staging 记录发布到项目目录，并核对文件是否齐全。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `staging_metadata` | object / string | 是 | — | — |
| `project_dir` | string | 否 | — | — |

### `publish_to_community`

发布到社区市场。本实现没有可写目标 → capability_unavailable + 替代路径。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `artifact_path` | string | 是 | — | — |
| `title` | string | 否 | — | — |
| `description` | string | 否 | — | — |

### `register_java_items`

生成 Java 物品注册（Fabric: Registry.register / NeoForge: DeferredRegister）+ 模型 + 语言文件。

items 每项：{id, name, name_en, stack_size}。贴图取当前模型的渲染图。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | write | — |
| `dest_path` | string | 否 | — | — |
| `namespace` | string | 否 | — | — |
| `asset_id` | string | 否 | — | — |
| `items` | array / null | 否 | None | — |
| `dry_run` | boolean | 否 | False | — |

### `render_inventory`

把当前模型渲染成 64×64 背包位图（最近邻，像素风）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 否 | — | — |
| `size` | integer | 否 | 64 | — |
| `output` | string | 否 | — | — |

### `scaffold_mod`

生成可编译的 Fabric / NeoForge 工程（loader/Loom/Gradle 版本现查）。

minecraft_version 支持 1.16~1.21.11 的旧命名与 26.1/26.2/26.3 新命名：
26.x 自动切 JDK 25、Gradle 9、net.fabricmc.fabric-loom（无 mappings）
或 ModDevGradle 2.x，wrapper 也按目标版本固定。
include_geckolib 只加依赖备注；include_mesh_model 忽略（本实现只出立方体模型）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `mod_id` | string | 是 | — | — |
| `loader` | string | 否 | fabric | — |
| `display_name` | string | 否 | — | — |
| `description` | string | 否 | — | — |
| `project_dir` | string | 否 | — | — |
| `minecraft_version` | string | 否 | 1.21.1 | — |
| `include_geckolib` | boolean | 否 | False | — |
| `include_mesh_model` | boolean | 否 | False | — |

### `texture_3d_model`

模型创建第 3 步：给当前模型上贴图（程序化调色板像素图，16×N 色带）。

没有可用的 retexture 服务时，按语义部位分配色带，
分辨率取 8–128（Minecraft 风格默认 16）。reference_image 只用于取主色，
不做风格迁移。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `style_prompt` | string | 否 | — | — |
| `reference_image` | string | 否 | — | — |
| `resolution` | integer | 否 | 16 | — |
| `palette` | array / null | 否 | None | — |

### `ui_asset_set`

资产集登记：把图标/九宫格/贴图绑到某个布局上，校验布局存在。action=write|read。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | write | — |
| `asset_set_id` | string | 否 | — | — |
| `name` | string | 否 | — | — |
| `platform` | string | 否 | java | — |
| `surface` | string | 否 | screen | — |
| `preview_asset_id` | string | 否 | — | — |
| `assets` | array / null | 否 | None | — |
| `layout_id` | string | 否 | — | — |
| `layout_sha256` | string | 否 | — | — |
| `evidence` | string | 否 | — | — |
| `geometry_evidence_paths` | array / null | 否 | None | — |

### `ui_layout`

布局 DSL：元素盒模型 + 越界/重叠/约束校验 + PNG 预览。action=write|read|preview。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 否 | write | — |
| `layout_id` | string | 否 | — | — |
| `expected_previous_hash` | string | 否 | — | — |
| `name` | string | 否 | — | — |
| `platform` | string | 否 | java | — |
| `surface` | string | 否 | screen | — |
| `canvas` | object / null | 否 | None | — |
| `viewport` | object / null | 否 | None | — |
| `panel` | object / null | 否 | None | — |
| `elements` | array / null | 否 | None | — |
| `variants` | array / null | 否 | None | — |
| `reserved_rects` | array / null | 否 | None | — |
| `constraints` | array / null | 否 | None | — |
| `evidence_path` | string | 否 | — | — |

### `validation_plan`

本轮验收计划：范围、必须过的闸门、交付物、通过标准、什么情况停手。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `scope` | string | 否 | project | — |
| `required_gates` | array / null | 否 | None | — |
| `deliverables` | array / null | 否 | None | — |
| `acceptance_criteria` | array / null | 否 | None | — |
| `stop_conditions` | array / null | 否 | None | — |

### `view_3d_model`

把当前模型渲染成等距预览图（离线软光栅，能看清造型与配色）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `note` | string | 否 | — | — |
| `size` | integer | 否 | 640 | — |

### `web_search`

联网搜索。本实现不接搜索服务，改用宿主 agent 自带的搜索。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | — | — |
| `scope` | string | 否 | minecraft | — |
| `language` | string | 否 | auto | — |
| `minecraft_version` | string | 否 | — | — |
| `loader` | string | 否 | — | — |
| `mod_hint` | string | 否 | — | — |
| `max_results` | integer | 否 | 8 | — |

