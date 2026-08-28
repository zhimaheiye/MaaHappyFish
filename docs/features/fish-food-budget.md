# 功能档案：鱼食预算计算 (fish-food-budget.md)

## 功能概述
在启动挂机任务时，根据玩家设置的海星容量、当前余粮和计划挂机时长，推算出需要补充的鱼食袋数，辅助玩家做好资源规划。

## 触发点与核心算法
- **触发**: `CollectFishTask` 启动首节点绑定 Custom Recognition `CalcFishingFoodReco`，任务拉起即刻执行识别与计算。
- **算法模型**:
  ```python
  rate = capacity / current_duration
  extra_food = (hangup_minutes - current_duration) * rate
  bags = ceil(extra_food / 30)
  ```

## UI 配置与输出展示
- **UI 依赖 (interface.json)**:
  提供三个输入型配置项：
  1. 海星单次容量
  2. 当前存粮可维持时长 (分钟)
  3. 计划挂机至此时长 (分钟)
- **输出端**: 
  - **Stdout 追踪**: 静默输出详细规划到 Python `stdout` 并持久化记录于客户端日志 `client_avalonia/logs/log-YYYYMMDD.log`。
  - **MFA UI 日志面板**: `CalcFishingFoodReco.analyze()` 在计算完成后，通过 `context.override_pipeline` 动态覆盖当前节点 `CollectFishTask` 的 `focus.Node.Recognition.Succeeded` 字段，随后返回命中 `(0, 0, 10, 10)`，使 MFAAvalonia 在任务开始第 1 毫秒即在日志面板展示单行动态预算规划（如：`[鱼食预算] 挂机至 08:00 (共 10.2h) | 缺口 493分钟 | 需备鱼食: 412粒 (约 14袋)`）。

## 迭代与 Debug 因果日志

### 2026-08-28 · 解决 focus 事件类型 Key 匹配缺失导致 UI 未渲染
- **现象**: `CalcFishingFoodReco` 计算并注入成功，但 MFAAvalonia 面板依然未展示。
- **根因**: 日志抓包显示 `analyze` 内部覆写当前节点的 `focus` 时，当前正在结算的 Recognition 阶段已完成上下文加载，挂载的 `focus` 顺延在随后的 `Node.Action.Starting` / `Node.Action.Succeeded` 事件中生效；原代码仅注入了 `Node.Recognition.Succeeded` 单个 key，导致 MFAAvalonia 在收到 Action 类事件时 key 不匹配而丢弃。
- **修复**: 在 `focus` 字典中全量挂载 `Node.Action.Starting`、`Node.Action.Succeeded`、`Node.PipelineNode.Succeeded` 与 `Node.Recognition.Succeeded` 全部事件通道，确保 100% 触发 UI 渲染。
- **回归**: 重新启动任务，MFAAvalonia 日志面板在任务拉起后立即展示鱼食缺口与袋数。

## 独立运行版本
考虑到玩家有时只想单独算一下，提取了核心逻辑制作成独立的本地 GUI 小工具。
- **路径**: `tools/fish_food_calculator.py`
- **实现**: Python Tkinter 原生界面。

## 当前状态
- **状态**: 生产就绪。
- **关键文件**: 
  - `agent/my_reco.py` (`CalcFishingFoodReco`)
  - `assets/resource/pipeline/collect_fish.json` (`CollectFishTask`)
  - `assets/interface.json`

