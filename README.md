# mc-agent-mcp — 我的世界创作/开发 MCP server

一个跑在本地的 MCP server，把「做 Minecraft 资产与工程」这件事拆成 **22 个家族 / 51 个工具**，agent 可以直接调。主线是：

**概念 → cube 模型 → 绑骨/动画 → 贴图/自发光 → 物品图标 / Java 物品 / 界面 → 实例运行与 Gradle 构建 → 打包发布**

设计原则只有一条：**本地确定性能力直接执行；需要外部服务的能力显式返回 `capability_unavailable` 并给替代路径，不伪造回执。** 没有工具回执，就不算成功。

## 目录

| 路径 | 内容 |
| --- | --- |
| `mc_agent/` | MCP server 本体：工具注册、资产管线、绑骨、贴图、界面、实例、图像后端 |
| `mc_craft_mcp/` | 底层库：实例/安装/启动、Gradle 构建、脚手架、资源包、贴图与模型 |
| `skills/` | 5 个工作流技能（资产贴图、mod 开发、打包、运行时自检、通用 craft） |
| `docs/tools.md` | 51 个工具的完整清单（由 server 自身生成，含参数与说明） |
| `tests/` | 冒烟测试、MCP 协议握手、底层库 smoke |
| `scripts/gen_tools_doc.py` | 从运行中的 server 重新生成 `docs/tools.md` |

## 安装

```powershell
git clone https://github.com/XiaoYuan08-Mc/mc-agent-mcp.git
cd mc-agent-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

装完会得到 `mc-agent` 命令（入口 `mc_agent.server:main`）。

## 接入客户端

仓库自带 `.mcp.json`，Claude Code / Cursor / WorkBuddy 等直接识别：

```json
{
  "mcpServers": {
    "mc-agent": {
      "command": "mc-agent",
      "args": [],
      "env": { "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

只用源码、不装包时改成绝对路径：

```json
{
  "mcpServers": {
    "mc-agent": {
      "command": "C:\\path\\to\\mc-agent-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mc_agent.server"],
      "env": { "PYTHONPATH": "C:\\path\\to\\mc-agent-mcp", "PYTHONUTF8": "1" }
    }
  }
}
```

HTTP 调试：`MCC_TRANSPORT=http MCC_PORT=8765 mc-agent`。

## 自检

```powershell
python tests/smoke_mc_agent.py     # 51 工具全链路（42 项断言）
python tests/mcp_client_check.py   # 真实 MCP 协议握手 + 调用
python tests/smoke_test.py         # 底层库 smoke（--full 会真的 scaffold + gradle build）
```

测试状态落在系统临时目录（`mc-agent-test`），不污染仓库。所有可变状态都能用 `MCC_HOME` 改根目录。

## 版本支持（脚手架）

`scaffold_mod` 不写死版本：`minecraft_version` 填哪个，loader / Fabric API / Loom / NeoForge / ModDevGradle 就现查哪个，查不到直接报错，不猜。

| Minecraft | 加载器 | JDK | Gradle | 模板要点 |
| --- | --- | --- | --- | --- |
| 1.16.5 ~ 1.21.11 | Fabric（Loom 1.7 / 1.9） | 8 / 11 / 17 / 21 | 8.10 | 传统 `fabric-loom` + `loom.officialMojangMappings()` + `modImplementation` |
| 1.20.2 ~ 1.21.11 | NeoForge（ModDevGradle 2.x） | 17 / 21 | 8.10 | `neoForge { version }` + `META-INF/neoforge.mods.toml` |
| 26.1 / 26.2 / 26.3 | Fabric（Loom 1.19+） | 25 | 9.8.2 | 插件 id `net.fabricmc.fabric-loom`，**无 mappings**，依赖走 `implementation` |
| 26.1 / 26.2 / 26.3 | NeoForge（26.x 版本线） | 25 | 9.2.1 | MDK 布局：`templates`/`neoforge.mods.toml`、foojay toolchain、`runs`/`mods` |

26.3 的实测解析与构建结果（本机验证，非模板推测）：

- Fabric Loader `0.20.1`，Fabric API `0.166.2+26.3`，Loom `1.19.4`，Gradle `9.8.2` → `./gradlew build` 成功，产物 `build/libs/*.jar`
- NeoForge `26.3.0.115`，ModDevGradle `2.0.148`，Gradle `9.2.1`，JDK 25 toolchain
- 资源包 `pack_format`：1.21.9–1.21.10 = 69、1.21.11 = 75、26.1.x = 84、26.2 = 88、**26.3 = 97**；1.21.9 起 `pack.mcmeta` 还要写 `min_format`/`max_format`（26.3 为 `[97,0]`–`[97,1]`）

JDK 由 `gradle_build` 显式选择：低于目标版本直接拒绝构建，扫描顺序是 `MCC_JAVA_HOME` / `JAVA_HOME` → scoop → Program Files，安装 JDK 25 后无需改代码。

## 工具家族

| 家族 | 工具数 | 做什么 |
| --- | --- | --- |
| 资产管线 | 10 | 概念 → 参数化 cube 树 → 程序化贴图 → 动画 → 等距渲染 → bbmodel/资源包/GeckoLib/GLB |
| 绑骨 | 5 | 分件（outliner + 高亮图 + 几何哈希 receipt）→ 语义表 → 分组 → 运动裁决 → 骨骼落地 |
| 方块贴图 / 自发光 | 4 | 材质关键词 → 16/32px 程序化贴图 + blockstate/model 全套；亮度阈值 → mask → overlay |
| 物品视觉 | 3 | 模型/图片 → 32px 图标（抠背景 + 包围盒 + 调色板量化）；Java 物品注册 + 模型 + lang |
| 实例与构建 | 12 | 实例创建/补齐/启动/日志、Gradle 构建、mod 脚手架、文件级热更 |
| API 与知识 | 2 | 37 条离线 API 语料，符号加权检索 + 物理侧过滤 |
| 会话状态 | 3 | 资产台账、验收计划、项目简报（JSON 落盘，跨进程存活） |
| 界面 | 4 | Java Screen 骨架、Bedrock JSON-UI、布局盒模型 + PNG 预览 |
| 图像 / 三维 | 3 | 多后端出图；GLB/OBJ → 体素化 → 3D 贪心合并 → bbmodel |
| 游戏内 | 2 | Win32 SendInput 注入键鼠；F2 取帧 + GDI 抓屏兜底 |
| 外部服务 | 4 | 社区发布/浏览/下载、联网搜索 → 显式 `capability_unavailable` |

完整参数说明见 [`docs/tools.md`](docs/tools.md)。

## 能力边界

**能本地确定性做的**：模型/贴图/图标/界面生成、资源包与 bbmodel/GLB 导出、体素化、实例管理、Gradle 构建、离线 API 检索。

**要走外部服务的**：

| 能力 | 怎么走 | 前提 |
| --- | --- | --- |
| 生成式图像 | `generate_image`：pollinations（免 key，每 IP 45 秒 1 张）/ OpenAI 兼容 / 本地 SD WebUI / ComfyUI | 免费档有速率限制；要快就自带 key 或跑本地 |
| image-to-3D | `generate_3d_model(provider="meshy")` → 轮询到 glb 后自动 `convert_to_cubes` | 需要 `MESHY_API_KEY`（付费） |
| 游戏内键鼠 + 截图 | `mc_game_test` 注入键鼠；`mc_capture` 优先 F2 让游戏自己存图，兜底 GDI 抓屏 | 目标窗口必须前台；独占全屏/UIPI 提权可能失效 |
| 社区市场 / 联网搜索 | 返回 `capability_unavailable` + 替代（宿主搜索、Modrinth 公开 API） | 本实现不内置这些服务端点 |

**说清楚的局限**：曲面体素化会出「台阶」（这是 MC 的造型语言，不是精度损失，`resolution` 上限 64）；语义标注需要调用方给（本地没有视觉模型）；热重载是文件级更新 + 提示重启，不做进程内替换。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `MCC_HOME` | 实例与运行状态的根目录（默认 `%LOCALAPPDATA%\mc-craft`） |
| `MCC_TRANSPORT` / `MCC_PORT` | `http` 时监听 `127.0.0.1:8765`（或指定端口） |
| `MC_AGENT_SKILLS` | 技能根目录，默认仓库 `skills/` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | OpenAI 兼容图像后端 |
| `POLLINATIONS_TOKEN` | 解除 pollinations 限速 |
| `MESHY_API_KEY` | image-to-3D |
| `SDWEBUI_URL` / `COMFYUI_URL` | 本地图像后端地址 |
