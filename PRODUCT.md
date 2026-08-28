# 全局架构约束 (PRODUCT.md)

## 项目定位与技术栈
- **项目定位**: 纯视觉自动化辅助工具，不干涉游戏封包，不含任何破解性质。
- **技术栈**: MaaFramework (C++ 核心) + Python Agent (复杂逻辑控制) + MFAAvalonia (桌面 UI)
- **目标设备**: MuMu 模拟器 v5+，通过 ADB (127.0.0.1:16416) 控制。

## 数据流架构
1. **用户交互 (MFAAvalonia)**: 读取 `interface.json` 渲染 UI 选项，下发任务配置。
2. **流水线分发 (MaaFramework)**: 加载 `collect_fish.json`，执行模板匹配/OCR 等基础识别和点击动作。
3. **状态管控 (Python Agent)**: 
   - 跨节点计时与状态保持 (如 `CheckStarfishTimerReco`, `CheckDutyCycleReco`)。
   - 复杂计算 (如 `CalcFishingFoodAction`)。
   - stdout 打印日志记录。
4. **日志渲染**: 
   - Python stdout 流入 `client_avalonia/logs/log-*.log`。
   - 动态 UI 日志通过 `context.override_pipeline` 注入 `focus` 字段显示。

## 禁止事项（负向边界）
1. **绝对禁止**：实现任何涉及付费（氪金）的自动化操作。
2. **暂不实现**：鱼苗养殖自动化、宝石兑换功能。
3. **日志输出限制**：**严禁在 Python print 中使用任何 Emoji 字符**。Windows 控制台默认 GBK 编码不支持 Unicode Emoji，会导致 Python 进程 `UnicodeEncodeError` 崩溃。
4. **界面同步限制**：**严禁仅修改某一处 `interface.json`**，修改 `assets/interface.json` 后必须手动复制到 `client_avalonia/` 和 `client/`。

## 关键架构决策及其理由
- **万能过渡节点 (ResumeHarvest)**
  - **决策**: 引入 `timeout: -1` 的 `DirectHit` 节点作为任务循环中转枢纽。
  - **理由**: MFA 节点在命中后 timeout 会重置。设置普通 timeout 可能导致前序任务（如喂食后返回）因未及时衔接到目标状态而直接崩溃中断整个 Pipeline。
- **Python 时钟接管计时 (Wall-clock Time)**
  - **决策**: 放弃 Pipeline 自带的 `timeout` 机制处理长周期定时，改用 Python `time.time()` (如 `CheckStarfishTimerReco`)。
  - **理由**: 任务循环频繁匹配目标时，Pipeline `timeout` 会不断重置，导致定时器永远无法触发。解耦后计时彻底独立。
- **动态 UI 日志注入 (Context.override_pipeline)**
  - **决策**: 使用 `context.override_pipeline` 动态修改 Pipeline 节点 `focus` 字段来呈现带时间戳的状态。
  - **理由**: MFAAvalonia 面板只渲染 `MonitorLog` 消息，而 Agent Stdout 仅写入本地文件。
- **Agent CLI 参数解析退化防御**
  - **决策**: Python 侧解析 `sys.argv` 优先匹配 `socket_id=` 前缀。
  - **理由**: 客户端传入参数格式不保证末尾一定为 `socket_id` (实际末尾可能为 `instance_name`)，避免启动崩溃。
