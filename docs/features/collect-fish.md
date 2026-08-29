# 功能档案：收鱼产物与巡检收宝 (collect-fish.md)

## 功能概述与设计目标
- **核心目标**: 持续或周期性自动收取鱼类产出的金币/宝石。
- **运行模式**: 支持无间断实时收取，或按“占空比”周期休眠后集中收取（降低资源占用）。

## Pipeline 节点拓扑图
```mermaid
graph TD
    A[CollectFishTask (入口)] --> B[ResumeHarvest]
    B -->|DirectHit| C{分发判断}
    C --> D[HandleShellPage]
    C --> E[CloseFeedPopup]
    C --> F[TriggerStarfishFeed]
    C --> G[CheckDutyCycle]
    C --> H[ClickFishBubble]
    H -->|找金币气泡| B
```
- **核心识别**: `TemplateMatch` 金币气泡.png (`ROI: [428,126,679,360]`, `threshold: 0.75`)
- **循环机制**: `ResumeHarvest` `timeout: -1` 为无底洞中转，保证 Pipeline 存活。

## 状态机设计 (CheckDutyCycleReco)
- **实现层**: Python Custom Recognition (`my_reco.py`)
- **状态流转**: `IDLE` (休眠) ↔ `ACTIVE` (密集收宝)
- **机制**: 
  - 初始化为 `IDLE`。
  - 休眠满 `idle_interval` 秒（由 UI 下拉框下发参数，如 30秒/5分/30分等）后切至 `ACTIVE`。
  - 激活持续 `active_duration`（硬编码 120 秒）后切回 `IDLE`。

## 迭代与 Debug 因果日志

### 2026-08-28 · GBK Emoji 崩溃
- **现象**: 状态切换时 print() 含 Emoji，Agent 进程静默崩溃，后续自定义识别/动作全部失效。
- **根因**: Windows 控制台默认 GBK 编码，Python 输出 Unicode emoji 时抛 `UnicodeEncodeError`。
- **修复**: 清除所有 print() 中的 emoji，改用纯中文标记符。
- **回归**: 重新运行任务，日志文件中 `[src=Agent][op=Stdout]` 正常出现且无截断。

### 2026-08-28 · UI 日志面板空白
- **现象**: Python print() 有输出（见 log 文件），但 MFAAvalonia 右侧日志面板无任何 Agent 自定义内容。
- **根因**: MFAAvalonia 日志面板仅渲染框架层 `MonitorLog` 回调消息，不渲染 `[src=Agent][op=Stdout]`，这是 UI 架构层设计限制。
- **修复**: 利用 Pipeline 节点的 `focus` 字段（ProjectInterface V2 消息模板机制），在状态切换时通过 `context.override_pipeline()` 动态注入 `CheckDutyCycle` 节点的 `focus` 内容，触发 MFAAvalonia 的 `Node.Recognition.Succeeded/Failed` 回调并渲染到日志面板。
- **回归**: 已验证 UI 面板正常显示「[巡检收宝] 进入休眠等待...」等消息。

### 2026-08-28 · UI 播报过于频繁（每 2 秒一条）
- **现象**: 休眠期间日志面板每隔 2 秒刷新一条相同内容「待机休眠中，预计 19:23:51 开始收宝」。
- **根因**: IDLE 循环每 2 秒返回 `Recognition.Succeeded`，每次均触发 `focus` 播报，且 focus 内容在此期间保持不变。
- **修复**: 在 `duty_state` 中增加 `last_ui_log_time` 和 `ui_log_interval`（默认 60 秒）；IDLE 循环内未到播报间隔时注入空 `focus: {}`（静默），到达间隔时才更新 focus 内容并播报（含剩余时间）。
- **回归**: 重新运行后日志面板每分钟最多一条状态消息，状态切换事件仍即时播报。

### 2026-08-29 · 静止画面熔断

- **现象**：游戏退出、卡死或 ADB 截图冻结后，`ResumeHarvest` 因 `timeout: -1` 继续无限识别，MFA 仍显示任务运行中。
- **保护**：`CheckScreenStallReco` 对主循环画面做降采样比较；连续 30 秒几乎没有画面变化时，触发 `StopTask` 并提示检查游戏或截图状态。
- **边界**：该保护防止“假运行”，不认定某一张启动图是原始退出原因，也不会尝试盲目点击重启游戏。

## 当前状态与未完成项
- **状态**: 生产就绪，核心功能与 UI 日志均已验证。
- **已完成**:
  - [x] 收鱼产物无限循环
  - [x] 巡检收宝 IDLE/ACTIVE 状态机
  - [x] MFA UI 日志面板动态状态播报（focus 注入机制）
  - [x] 播报节流（每 60 秒最多一次）
- **暂不实现**: 鱼苗养殖、宝石兑换、任何付费操作。

## 关键文件入口
- `assets/resource/pipeline/collect_fish.json` — Pipeline 拓扑（含 focus 静态配置）
- `agent/my_reco.py` — `CheckDutyCycleReco` 状态机 + focus 注入逻辑
