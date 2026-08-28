# 功能档案：鱼食预算计算 (fish-food-budget.md)

## 功能概述
在启动挂机任务时，根据玩家设置的海星容量、当前余粮和计划挂机时长，推算出需要补充的鱼食袋数，辅助玩家做好资源规划。

## 触发点与核心算法
- **触发**: `CollectFishTask` 启动首节点绑定 Custom Action `CalcFishingFoodAction`，任务拉起即刻执行。
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
  - **MFA UI 日志面板**: 计算完成后通过 `context.override_pipeline` 动态注入紧邻的桥接节点 `LogFoodBudget` 的 `focus.Node.Action.Succeeded` 字段，以静默非阻塞形式在右侧日志面板输出单行摘要提示（如：`[鱼食预算] 挂机至 08:00 (共 12.6h) | 缺口 638分钟 | 需备鱼食: 532粒 (约 18袋)`）。

## 迭代与 Debug 因果日志

### 2026-08-28 · 鱼食预算未在 UI 日志面板展示
- **现象**: 启动任务时控制台文件有输出，但 MFAAvalonia 界面日志面板中只有 `[收鱼任务] 启动成功...`，缺失鱼食计算结论。
- **根因**: 原先鱼食计算仅依赖 Python `print()` 输出，未注入到 Pipeline 节点的 `focus` 属性中；且直接在当前 Action 节点注入当前节点的 focus 存在时序竞争风险。
- **修复**: 在 `CollectFishTask` 与 `ResumeHarvest` 之间插入轻量桥接节点 `LogFoodBudget`（`DirectHit` + `DoNothing`）；`CalcFishingFoodAction.run()` 在计算完毕后将格式化的预算摘要动态注入到 `LogFoodBudget` 的 `focus.Node.Action.Succeeded`，完成启动瞬间的单次安全播报。
- **回归**: 重新启动任务，MFAAvalonia 界面日志面板在任务开始后立即展示计算得到的挂机缺口与需备袋数。

## 独立运行版本
考虑到玩家有时只想单独算一下，提取了核心逻辑制作成独立的本地 GUI 小工具。
- **路径**: `tools/fish_food_calculator.py`
- **实现**: Python Tkinter 原生界面。

## 当前状态
- **状态**: 生产就绪。
- **关键文件**: 
  - `agent/my_action.py` (`CalcFishingFoodAction`)
  - `assets/resource/pipeline/collect_fish.json` (`CollectFishTask` -> `LogFoodBudget`)
