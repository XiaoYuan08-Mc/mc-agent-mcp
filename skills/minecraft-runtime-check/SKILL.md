---
name: minecraft-runtime-check
description: 用本地实例验证 Minecraft 交付物：补运行时、启动、读日志、必要时停止。用户要求「装进去看看 / 启动测试 / 看报错」时使用。
---

# 运行时验证

## 证据阶梯（低 → 高）

1. 文件已生成（`mc_install` 回执含 `sha256`）
2. 运行时齐全（`mc_runtime(action="ensure")` 返回 `exit_code=0`）
3. 进程启动（`mc_runtime(action="launch")` 返回 `pid`，`status.running=true`）
4. 日志无异常且有你的加载行（`mc_logs` 的最新行）
5. 游戏内画面/交互正确（**需要截图或用户确认**，本套件没有自动截图）

只到第 3 步就报告"测试通过"是错的。

## 标准动作

```
mc_instance(action="locate", name="...")     # 确认目标实例
mc_runtime(instance="...", action="ensure")  # 首次必做：补版本+loader，不启动
mc_runtime(instance="...", action="launch")
mc_runtime(instance="...", action="status")  # 5~15 秒后再查一次
mc_logs(instance="...", lines=120)
```

## 常见失败

| 现象 | 判断 |
| --- | --- |
| `ensure` 非 0 | 版本/loader 名写错、网络不通、磁盘不足；先看 `install.log` |
| `launch` 起来了但秒退 | 看 `launch-*.log` 末尾异常：Java 版本、mixin、mod 冲突 |
| 日志有 mod 加载行但进不去世界 | 资源/注册问题，不是启动问题 |
| 同一实例反复启动 | 先 `status`，再决定；不要连开两个进程抢同一实例目录 |
| 需要重来 | `mc_runtime(action="stop")` 干净结束，再 launch |

## 纪律

- 一个实例一次只跑一个进程。
- 报错先分类（环境 / 版本 / 依赖 / 代码），再改；不要靠反复重启碰运气。
- 停止要留给用户选择：`stop` 会杀进程树，游戏未保存会丢进度。
- 基岩版没有本地实例可跑：本套件不启动基岩版，只能打包交付。
