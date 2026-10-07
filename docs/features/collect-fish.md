# 功能档案：收鱼产物与单/双缸收宝 (collect-fish.md)

2026-10-07：到点好友摸宝的 Focus 文案改为“十点、二十二点”，避免 MFAAvalonia 路径解析告警；触发时间、落盘去重与返回收鱼逻辑不变。代码级验证完成，本次未操作 MFA/模拟器。

> 本文描述「收鱼产物」挂机收宝任务。支持「当前单鱼缸」挂机（支持占空比休眠）与「双鱼缸轮换（1缸与2缸）」持续实时收宝，两者均统一集成鱼缸管理页通用三海星喂食。若需依次切换 1/2/3 缸并带每小时扩展等复杂日常巡视，见 `docs/features/patrol.md`。

## 功能概述与设计目标

2026-10-02：单/双缸挂机到点插入的十二点日常、十点/二十二点好友摸宝，改为启动前落盘自然日日期。Agent 重建后同档不会再次自动触发；日期是已尝试记录，不是业务完成记录，返回栈仍仅留在当前进程。Recognition 无落盘副作用，写入失败时不启动子任务。详见 [daily-routine.md](daily-routine.md)；跨进程专项代码级通过，未做实机测试。
- **核心目标**: 持续或周期性自动收取鱼类产出的金币/宝石，并定时通过鱼缸管理页通用入口喂满三只海星（萌海星、乖海星、亮海星）。
- **运行模式**:
  1. **当前单鱼缸（默认）**: 保持在当前鱼缸内收宝。支持无间断实时收取，或按“占空比”（`CheckDutyCycle`）周期休眠后集中收取（降低资源占用）。
  2. **双鱼缸轮换（1缸与2缸）**: 在 1 缸与 2 缸之间按设定的时间间隔（如 30秒/1分钟/1.5分钟/2分钟[默认]/3分钟/5分钟）自动来回切换收宝。**双缸模式固定持续实时收宝**（跳过 `CheckDutyCycle` 休眠），最大化高产鱼的收宝频率。
- **通用海星喂食**: 无论单缸还是双缸模式，海星喂食统一通过“鱼缸管理 → 海星 → 萌海星/乖海星/亮海星”入口一次喂满三只海星，不再使用旧版右上角齿轮单个海星喂食。
- **到点插入（可选）**: 默认开启「十二点日常收尾」：当天 12:00 后自动跑一遍日常收尾（子任务全选），完成后回到收鱼。可选「十点/二十二点好友摸宝」，用于清掉未手动处理的好友体力；每个时段每天一次。

## 核心状态机与单调时间片调度设计

双鱼缸轮换模式必须保证无论中途插入海星喂食耗时多久，或者发生页面瞬时重试，都能严格对齐到物理时间轴：

1. **基准时间锚点 ($t_0$)**：
   - 任务启动时，首先执行通用三海星喂食（若启用了海星喂食且尚未初次喂食）；
   - 随后切至 1 缸并完成主界面数字校验；
   - 确认处于 1 缸后，调用 `CollectFishDualStartAction` 记录当前单调时钟基准时间 $t_0 = \text{time.monotonic()}$，初始化当前槽位 $slot = 0$、目标缸 $current\_tank = 1$。
2. **单调时间片计算公式**：
   $$slot = \left\lfloor \frac{\text{now} - t_0}{\text{switch\_interval}} \right\rfloor$$
   $$\text{expected\_tank} = 1 \quad (\text{若 } slot \bmod 2 == 0) \quad \text{else} \quad 2$$
3. **状态驱动切换与防追赶**：
   - 每次收宝主循环中，`CheckCollectFishTankSwitchReco` 计算当前时刻的 $\text{expected\_tank}$；
   - 只有当 $current\_tank \ne \text{expected\_tank}$ 时才触发切缸，严禁简单的布尔反转（toggle）；
   - 当海星喂食跨越了一个或多个时间片边界时，喂食结束后由 `CollectFishAfterStarfishAction` 立即重新评估当前时刻的 $\text{expected\_tank}$。若发现跨边界，立即标记切缸需求并在返回鱼缸后由状态机顺滑过渡到当前时刻对应的目标鱼缸，绝对不会发生多重连环切换或死循环。

## Pipeline 节点拓扑图
```mermaid
graph TD
    A[CollectFishTask (入口)] --> SetParam[设置模式与间隔]
    SetParam --> StartRouter{CollectFishStartRouter}
    StartRouter -->|双缸模式且未初始化| Normalize[CollectFishDualStartNormalize 归一化至1缸]
    Normalize --> StartDual[CollectFishDualStartAction 记录t0]
    StartRouter -->|单缸模式| StartSingle[CollectFishSingleStartAction]
    StartDual --> ResumeHarvest[ResumeHarvest]
    StartSingle --> ResumeHarvest

    ResumeHarvest -->|DirectHit| Dist{分发判断}
    Dist --> FeedTrigger{TriggerStarfishFeed 海星喂食到期}
    FeedTrigger --> OpenMgmt[CollectFishOpenManagement 鱼缸管理]
    OpenMgmt --> VerifyMgmt[CollectFishVerifyManagement]
    VerifyMgmt --> StarfishPage[CollectFishOpenUniversalStarfish]
    StarfishPage --> Feed3[顺序喂食 萌/乖/亮 三海星]
    Feed3 --> ReturnMgmt[CollectFishStarfishReturnToManagement]
    ReturnMgmt --> ReturnTank[CollectFishStarfishReturnToTank]
    ReturnTank --> StarfishRouter[CollectFishAfterStarfishRouter 识别返回缸号]
    StarfishRouter --> PostRouter[CollectFishAfterStarfishPostRouter]
    PostRouter -->|未初始化 is_inited=False| NeedsInit[CollectFishAfterStarfishNeedsInitialization]
    NeedsInit --> StartRouter
    PostRouter -->|已初始化 is_inited=True| ResumeHarvest

    Dist --> TankSwitch{CollectFishCheckTankSwitch 切缸到期}
    TankSwitch --> SwitchRouter{CollectFishSwitchTankRouter}
    SwitchRouter -->|目标=2缸| SwTo2[CollectFishSwitchToTank2Target]
    SwitchRouter -->|目标=1缸| SwTo1[CollectFishSwitchToTank1Target]
    SwTo2 & SwTo1 --> OpenPicker[CollectFishOpenTankPicker 打开选缸列表]
    OpenPicker --> SelectTarget[CollectFishSelectTargetTankEntry 点击目标缸条目]
    SelectTarget --> VerifyTarget[CollectFishVerifyTargetTank 校验主界面鱼缸数字]
    VerifyTarget -->|成功| RecordTank[CollectFishRecordSwitchedTankAction 更新缸号并清零重试]
    VerifyTarget -->|失败| RetrySwitch[CollectFishSwitchRetryAction 重试/3次熔断]
    RecordTank --> ResumeHarvest

    Dist --> D0[HandleShellEntryMisTouch 第一层误触门禁]
    Dist --> D[HandleShellPage 大章鱼主页门禁]
    Dist --> E[CloseFeedPopup]
    Dist --> Duty[CheckDutyCycle 单缸占空比休眠]
    Dist --> Shake[CollectFishShakeGem 摇一摇收宝]
    Dist --> Bubble[ClickFishBubble 点击气泡]
    Bubble --> Slide[鱼缸底部安全区左到右再右到左往复滑动]
    Slide --> ResumeHarvest
```
- **双鱼缸视觉门禁与安全机制**：
  - 切缸严格按照：点击当前鱼缸序号进入选缸列表 $\rightarrow$ OCR 选中目标序号条目（`[200, 240, 480, 260]`） $\rightarrow$ 校验主界面右上角鱼缸序号（`[1130, 23, 75, 45]`）。
  - **杜绝盲点固定坐标**：前置状态未达成或列表未打开绝不盲目下发点击。
  - **3次重试安全熔断**：切缸验证若连续失败 3 次，`CollectFishSwitchRetryAction` 触发 `StopTask` 停止任务并报错，杜绝死循环卡死。
- **核心识别**: `TemplateMatch` 金币气泡.png (`ROI: [428,126,679,360]`, `threshold: 0.75`)
- **双向扫底收取**: 每次气泡点击后立即执行 `(221,663) -> (1007,663)`，再按原轨迹 `(1007,663) -> (221,663)` 滑回；两段均限制在用户指定安全范围 `[201,630,826,66]` 内，完成往复后才返回气泡识别循环。IMAGE、SHAKE 逐轮扫底、最终补刀与独立摇晃测试统一遵守该规则。
- **循环机制**: `ResumeHarvest` `timeout: -1` 为无底洞中转，保证 Pipeline 存活。
- **误入开贝壳恢复**：第一层入口页在 `[498,80,280,191]` 识别 `开贝壳_误触识别.png`，命中后才在 `[1,0,189,119]` OCR 点击左上角“返回”；若已进入第二层大章鱼主页，则仍先在 `[37,68,226,142]` 识别 `开贝壳_识别.png`，再在 `[0,0,250,150]` 识别并点击 `贝壳页面_返回.png`。两层门禁互不替代，返回识别失败时都不盲点。

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
- **保护**：`CheckScreenStallReco` 对主循环画面做降采样比较；连续 30 秒几乎没有画面变化时停止任务，并提示检查游戏或截图状态。
- **2026-10-06**：该停止改为无 `next` 的 `FailTaskAction`。`StopTask` 会被当成任务成功，界面同时出现运行保护提示和绿色「任务已全部完成」。

### 2026-10-06 · 亮海星鱼食未识别后停在管理页却报完成

- **现象**：v0.7.4 用户报告，收鱼产物只给萌/乖海星补充了鱼食。亮海星点了「补充」之后，界面停在鱼缸管理页，日志却出现「单鱼缸模式启动就绪，开始收宝」，约 30 秒后出现「画面长时间无变化」和绿色「任务已全部完成」。截图上的返回按钮盖着模拟器按键提示。
- **证据**：`台式机报错调查报告（待修复）\MaaHappyFish-TestReports`，2026-10-05 23:14–23:15。萌/乖普通鱼食袋分数约 0.944。亮海星普通鱼食袋 0.485、深海加号 0.428，都低于 0.85。同一帧「返回」OCR 约 0.999，框 `[63,30,58,33]`，已经被点击。随后三个鱼缸编号牌都未命中，`CollectFishSingleStartFallback` 直接把鱼缸 1 写成已就绪。本机 2026-10-06 11:09 的亮海星能命中普通鱼食袋，这条未知鱼食图没有现场截图，不新增模板。
- **根因**：
  1. 萌/乖/亮的喂食路由把「返回」和两种鱼食模板放在同一个 `next`。鱼食没中时，始终可见的「返回」会在同一帧胜出。
  2. 失败后只点一次返回就进入收宝。当时还在管理页，单缸启动又用 DirectHit 假装鱼缸 1，并写下 `is_inited`。
  3. 画面保护用 `StopTask`，失败被显示成完成。
- **修复**：
  1. 三个喂食路由先 OCR「选择喂食」（ROI `[560,70,420,160]`，覆盖现场框 `[621,107,104,34]`），最多等 4 秒，`next` 只剩两种已知鱼食。超时进入 `CollectFishFoodNotRecognized`，不点未知鱼食。
  2. 失败后先释放本轮计时并设置 60 秒退避，不调用 `CollectFishAfterStarfishAction`，因此不把失败写成喂食成功。然后最多点 3 次已证实的「返回」（ROI `[1,0,189,119]`），直到鱼缸 1/2/3 编号牌命中才回到收宝。次数只在 Action 里加一。仍看不到编号牌则 `FailTaskAction`。
  3. 单缸启动必须命中编号牌才调用 `CollectFishSingleStartAction`。只看到管理页标题「鱼缸」（ROI `[180,0,230,90]`）时，同样最多返回 3 次再复查。标题和编号牌都没有时直接失败，不点击。不再输出「单鱼缸模式启动就绪，开始收宝」。
- **Start Contract**：鱼缸 1/2/3 主页面可以开始收宝。鱼缸管理页可以有界返回后再认编号牌。没有这两种画面时停止。选择喂食弹窗本身仍然不能当作收鱼任务的任意起点。
- **验证**：`dev/test_collect_fish_dual_tank.py` 21 项、Pipeline 正则 273 条 / 899 节点、Agent 引用、全局弹窗覆盖通过。代码级验证完成，本次未做 MFA/模拟器测试。用户报告目录保留。同日下午的鱼食规则见下一节，未中之后不再返回并继续。

### 2026-10-06 · 三种金币鱼食

喂食先投放廉价、普通、高级。模板从选择喂食弹窗裁鱼食袋上半部分，文件是 `喂食_廉价鱼食.png`、`喂食_普通鱼食.png`、`喂食_高级鱼食.png`。三种都没有时，再认深海第一格的玫红字块 `喂食_深海鱼食.png`。红色库存数字不进入模板。`PickStarfishShellFoodReco` 按这个顺序找，`ClickRecognizedCenterAction` 点识别框中心。都没有时，`CollectFishFoodNotRecognized` 和独立入口的 `StarfishFoodNotRecognized_Standalone` 都是无 `next` 的 `FailTaskAction`。

默认位置：加号右边第一格是廉价，右边第二格是普通，加号正下方是高级。12:56 的实机弹窗上三张模板分数都是 1.0，并落在这三格。12:58 只点击了右边第一格的上半部分，萌海星直接补到 100/100，预计可喂食 2 小时。没有种类弹窗。纸袋图标是通用的。另外两格没有点击。购买侧同日各买 1 袋，金币减少 2000、8500、400，开心宝仍是 346。

代码级验证见 `dev/test_starfish_food.py`、购买、巡检、收鱼和日常鱼食参数专项，以及正则 286 条 / 911 节点、Agent 引用、三份界面字节一致。版本仍是 0.7.4。喂食整条任务没有跑 MFA。未提交、未发版。
### 2026-09-14 · [历史事故/已在v0.5.6修复] 双缸模式在鱼缸 2 启动假死（跨背景模板失配与 timeout: -1 死锁）
- **现象**: v0.5.5 时期用户在 MFA 启动双鱼缸轮换模式测试，当游戏停留在鱼缸 2 时，任务在输出首轮喂食日志后完全静默，无切缸、无收宝、无进入管理页，也不报错，静默等待数分钟仍无动作。
- **历史根因**:
  1. 跨背景模板失配：早期 `CollectFishOpenManagement` 使用截取自鱼缸 3（深海，深蓝背景）的 `patrol/鱼缸管理_扳手.png`。该模板在鱼缸 2（米黄木纹背景）因半透明玻璃球透色导致匹配分数降至 0.4916，低于门禁阈值 0.70，导致识别失败；
  2. 前驱死锁：早期 `TriggerStarfishFeed` 的 `timeout` 为 `-1`。MaaFramework 规定候选节点自身的 `timeout` 与 `on_error` 仅在候选节点被识别命中后才激活；候选识别返回 None 仅作为“未命中”，不会触发候选自身的 `on_error`，导致父节点陷入无限次轮询，静默假死；
  3. 入口缺乏鱼缸归一：早期流程在触发喂食前缺乏鱼缸状态感知与归一路由器。
- **v0.5.6 修复与替代方案**:
  1. 在 v0.5.6（commit `956b7e2`）中，将 `TriggerStarfishFeed` 的 `timeout` 设置为 `10000`ms，并接入 `on_error: ["CollectFishStarfishEntryFailed"]`，彻底消除父节点无限轮询；
  2. 重构入口识别体系：废弃易受背景色差干扰的半透明扳手模板，改为 `CollectFishStarfishEntryRouter` 分别匹配各缸固定特征的 `patrol/鱼缸1/2/3_主页面编号.png`（ROI `[40, 32, 45, 48]`，阈值 0.85），确认当前鱼缸后再精准点击管理入口 `(176, 54)`，彻底解决了跨鱼缸背景失配问题。

## 当前状态与未完成项
- **状态**: 生产就绪，核心功能、双缸轮换、通用海星喂食与 UI 日志均已通过代码级验证。
- **已完成**:
  - [x] 收鱼产物无限循环
  - [x] 巡检收宝 IDLE/ACTIVE 状态机（当前单鱼缸模式专享）
  - [x] 双鱼缸轮换（1缸与2缸）单调时间片调度与持续实时收宝
  - [x] 鱼缸管理页通用三海星喂食集成（萌海星 → 乖海星 → 亮海星）
  - [x] 海星喂食后跨时间片边界自适应校准与防追赶恢复
  - [x] MFA UI 日志面板动态状态播报（focus 注入机制）
  - [x] 播报节流（每 60 秒最多一次）
- **本任务不包含**: 鱼苗养殖、宝石兑换、任何付费操作；宝石礼盒兑换由独立 `GemGiftBoxTask` 负责。

2026-09-14 正式支持「双鱼缸轮换（1缸与2缸）」与通用三海星喂食：
- 增设「收鱼鱼缸模式」配置（默认「当前单鱼缸」，可选「双鱼缸轮换（1缸与2缸）」）；界面通过 ProjectInterface case 子选项联动显隐，单缸模式只显示「单缸收宝间隔」，双缸模式只显示「双缸切换间隔」（30秒/1分钟/1.5分钟/2分钟[默认]/3分钟/5分钟），公共参数保持显示；
- 单缸模式保留原逻辑与 `CheckDutyCycle` 占空比休眠；双缸模式固定持续实时收宝（跳过 `CheckDutyCycle`）；
- 严格基于单调时间 $slot = \lfloor(now - t_0)/interval\rfloor$ 判定期望鱼缸，彻底杜绝状态乱翻；
- 喂食流程统一重构为经由鱼缸管理页顺序喂满萌海星、乖海星、亮海星；喂食后自动比对当前时刻单调槽位完成目标缸补偿校准；
- 修复首轮海星喂食绕过双缸初始化问题：海星退出后经由 `CollectFishAfterStarfishPostRouter`，未初始化（`CheckCollectFishNeedsInitReco` 命中）严格导回 `CollectFishStartCheckMode` 执行归一与 $t_0$ 打桩，已初始化（挂机中周期喂食）直通 `ResumeHarvest` 保持 $t_0$；
- 切缸过程落实严格前置门禁：选缸列表打开确认、目标序号条目 OCR 定位点击、主界面右上角鱼缸数字识别验证；连续 3 次失败安全熔断；
- 专属测试套件 `dev/test_collect_fish_dual_tank.py` 现为 21 项，含 Case A~G。2026-09-14 当时为 20 项且未做模拟器测试；2026-10-06 的喂食失败与假完成修复见上文。

2026-09-12 已将误入开贝壳页的恢复拆为“页面本体确认 → 返回按钮点击”两步，避免鱼缸管理页的同款返回按钮被误认为大章鱼页面；已完成代码级验证，本次未做模拟器测试。

2026-09-14 用户重新提供第一层入口页模板 `开贝壳_误触识别.png`。收鱼循环现先区分第一层误触页与第二层大章鱼主页：第一层 OCR 点击左上角返回，第二层沿用专用返回模板；代码级验证完成，本次未做模拟器测试。

2026-09-12 新增独立实验任务 `ShakeGemCollectTestTask`（摇一摇收宝石（测试）），用于在主鱼缸验证 MuMu 原生后台 shake 连续模拟能否使鱼身上宝石脱落并由底部滑动收走；该实验任务完全独立，默认未勾选，严禁且未修改正式收鱼产物主干流水线。

2026-09-12 正式支持收宝石双模式（IMAGE 图像识别 / SHAKE MuMu摇晃）：
- 默认保持 `IMAGE` 图像识别模式，气泡检测与点击不变，底部收取统一升级为双向往复滑动；
- 选择 `SHAKE` 模式时，任务入口设置 `gem_collect_state["mode"] = "SHAKE"`，流水线在 `ClickFishBubble` 前命中 `CollectFishShakeGem`，执行严格交替的高频摇晃与双向扫底收宝循环（5 次摇晃 + 6 轮双向扫底补刀）。MuMuManager shake RPC 超时 5 秒；连续 3 次失败时跳过本轮剩余摇晃并扫底，然后继续挂机，不再把整次收鱼任务判失败。
- 2026-09-12 第二轮优化：增加每次摇晃后的充分沉降等待（`GEM_SHAKE_SETTLE_DELAY_SECONDS = 1.5s`）以及循环完成后的最终沉降等待（`GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS = 1.5s`），给空中飘落的宝石留出充足物理下落时间后再执行底部扫宝，彻底解决过早切缸导致宝石未收完的问题。
- 2026-09-16：v0.4.4 现场日志确认挂机两次「任务失败：收鱼产物」均由 `MuMuManager` shake RPC 连续 2 秒超时触发硬熔断。挂机路径超时改为 5 秒；连续 3 次失败改为跳过本轮剩余摇晃并扫底后继续 `ResumeHarvest`，不再中断整次收鱼。

## 关键文件入口
- `assets/resource/pipeline/collect_fish.json` — Pipeline 拓扑（含双缸切缸、通用海星喂食与 focus 静态配置）
- `assets/resource/pipeline/features/shake_gem_collect_test.json` — 摇一摇收宝石独立实验流水线
- `agent/runtime_state.py` — `collect_fish_state` 状态容器（模式、间隔、基准时间 $t_0$、当前缸等）
- `agent/my_action.py` — 双缸启动记录、缸号记录、重试熔断及海星喂食后状态校准
- `agent/my_reco.py` — `CheckCollectFishTankSwitchReco` 切缸单调时钟判断、`CheckDutyCycleReco` 单缸占空比、`CheckCollectFishNeedsInitReco` 启动初始化检测
- `dev/test_collect_fish_dual_tank.py` — 双鱼缸轮换与通用海星喂食专属单测（21 项，含 Case A~G）
