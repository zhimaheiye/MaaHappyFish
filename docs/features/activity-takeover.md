# 限时活动接管包

**状态（2026-10-13）**：从早期 `D:\happyfishgame` 工作树移植了 `DumpActivityTakeover` CustomAction、写包逻辑和测试，已注册到 Agent。当前正式任务的 Pipeline 没有引用此 Action，因此它不会改变日常任务行为，也不表示限时活动半自动化已接入或实机通过。

## 调用契约

活动编译器只有在识别失败、知识边界等需要人工或另一 Agent 接管时，才应生成 `action: "Custom"`、`custom_action: "DumpActivityTakeover"` 的节点。`custom_action_param` 至少提供 `session_dir`，并尽量提供 `event`、`session`、`source_state`、`reason`、`expected`、`roi`、`result_candidates`、`flow_path` 和 `pipeline_path`。Action 会以节点实际名称覆盖 `pipeline_node`。

Action 复用当前 Maa Controller 截取 720p 画面，在 `<session_dir>/takeover/<时间_原因_状态>/` 写 `current.png`、`trace_tail.jsonl`（至多 10 行）、`meta.json`；找到 Maa 日志时再写 `maa_log_tail.txt`（至多 200 行）。日志与 trace 缺失会记为 `unavailable`，不能捏造来源。截图缺失会使 Action 返回 False，调用方不得把写包或 `StopTask` 当成业务完成。调用方必须自己设计真实 FAILED 的终端节点和安全停止路径。

`session_dir` 是受信任的本地路径，由活动编译器提供；不要把未经验证的外部文本直接用作写包路径。接管包可能含真实游戏截图和日志，应按运行证据处理。

## 验证和限制

- `python -m unittest dev.test_activity_takeover -v`：覆盖中文路径、截图与 trace、缺日志、重复时间戳和日志定位；不连接模拟器。
- `dev/test_activity_takeover_live.py` 是从旧活动实验保留的人工冒烟脚本，依赖另一仓库 `happyfishagent` 的编译器和设备接口。运行前设置 `HAPPYFISH_AGENT_ROOT` 指向该仓库，先审查它生成的 Pipeline、连接设备和当前活动环境；本轮未运行。它只构造不可能命中的 OCR 和 `DoNothing`，不得据此宣布完整活动闭环已通过。
- 正式 Pipeline 尚未接线；尚无 MFA/MuMu 实测。未来接入时应先核验 `happyfishagent` 当前编译器契约，再按本仓库的失败节点规则和活动文档逐项验收。
