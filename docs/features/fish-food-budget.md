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

### 2026-08-28 · 鱼食预算改用 Custom Recognition 原生注入
- **现象**: 原先尝试通过 Custom Action 桥接节点注入 focus，但在任务队列拉起时可能受到 interface override 覆盖影响导致桥接节点未触发。
- **根因**: Custom Action 是在 Recognition 成功后才被调度的，对下一节点的 override 时序依赖较高；而 Custom Recognition 在节点一被解析执行时即刻调用 `analyze` 并直接向当前节点注入 `focus.Node.Recognition.Succeeded`，链路完全零时序竞争。
- **修复**: 将 `CollectFishTask` 重构为 Custom Recognition `CalcFishingFoodReco`，与已稳定运行的 `CheckDutyCycleReco` 保持一致的标准注入范式。
- **回归**: 单元测试模拟 `analyze()` 验证成功返回命中并正确覆写 focus 消息。

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

