# 好友摸宝自动化 (docs/features/friend-gem.md)

## 功能定位
开心水族箱好友巡访与金币产物收取自动化助手（`FriendGemTask`）。从主鱼缸、留言箱、星级好友列表或好友鱼缸自适应启动，依次进入好友水族箱；优先使用可用的快捷摸宝按钮，不可用时采集金币气泡。采用**状态确认完成（UI 状态驱动）**机制，以左侧体力栏出现「刷新体力」（灰电/0体力）作为该好友彻底清空的唯一准则。周末遇到【海牛先生】时不再跳过，而是进入共享喂食流程，识别到刷新体力后再继续下一位好友；全程避开付费刷新区域。

## ⚠️ 任务启动前置条件（重要）
- **入口 A**：主鱼缸页面，识别并点击右侧 `好友页面_入口.png`；若打开留言箱，按下述留言箱桥接进入列表。
- **入口 B**：位于「我的星级好友」列表页面顶部开始任务（顶部第 3 个 Tab，确保第 1 排好友卡片可见）。
- **入口 C**：位于任意好友水族箱内部开始任务（支持海牛先生页面）。
- **入口 D**：留言箱页面，在 `[40,90,660,80]` OCR 确认“未读留言最多保留”后点击第 3 页签 `[489,41,8,8]`，必须再确认“星级好友”才进入第一位好友。未知资料页、未确认列表均不盲点。
- 脚本自适应启动进入，并在好友之间通过右上角「下一位 (`>`)」药丸按钮连续巡访。

---

## 2026-10-02 主鱼缸入口停在留言箱修复

10:00:02 主鱼缸好友入口触摸已下发，但页面实际是留言箱，旧启动路由只接受星级好友列表/好友缸，10:00:24 超时使挂机兜底中断。现场实测第 2 页签 `(363,45)` 是个人资料，第 3 页签 `(493,45)` 才是“我的星级好友”；入口模板命中正确，无需重截。

新增共享 `[JumpBack]FriendPageMessageBoxToStarFriends`：留言箱独有文案确认后点击第 3 页签，5 秒内验证列表才回到原启动路由，失败显式 ERROR/StopTask。好友摸宝与海牛先生周末入口共同复用，原快捷摸宝、体力耗尽、好友序号与返回门禁保持不变。

新报告专项、好友摸宝、海牛与启动恢复测试及通用静态门禁代码级通过，本次未做 MFA/模拟器测试。报告摘要已迁入本节；`台式机报错调查报告（待修复）/好友摸宝兜底进留言箱_20261002` 本轮已核对不存在；其中附带台账的值守器分类缺陷另记在 [patrol.md](patrol.md) 与 `ISSUES.md`，不将它误记为好友导航未修复。

## 状态机流转设计

### 2026-10-02 日程重启复发补充

新增报告的 10:00 留言箱故障与前一批相同，当前共享留言箱桥接已修复，无需重复修改模板。11:31 终止并重建 Agent 后，11:36 上午档再次触发；11:42 未重建进程的启动则不重复。根因是三项日程日期仅保存在进程 dict。现启动前原子落盘，Agent 启动恢复日期，上午/晚上档每日各自动尝试一次；失败不等于完成，也不因重启再次自动触发。独立 `FriendGemTask` 不受日程日期拦截。详见 [daily-routine.md](daily-routine.md) 的日程契约；跨进程及窗口专项完成代码级验证，本次未做实机测试。

```text
FriendGemTask (入口，初始化好友状态并设置海牛返回模式为 friend_gem)
    ↓
FriendGemStartRouter (启动环境自适应路由器)
    ├─ 主鱼缸 ─> FriendGemOpenFriendPage (好友页面_入口.png) ─> 返回 StartRouter
    ├─ 留言箱 ─> FriendPageMessageBoxToStarFriends ─> 确认星级好友 ─> 返回 StartRouter
    ├─ 好友列表 ─> FriendGemStartFromFriendList (OCR「星级好友」) ─> 点击第1张卡
    ├─ 已在海牛页面 ─> FriendGemStartManateeTank ─> 海牛流程
    └─ 已在普通好友缸 ─> FriendGemStartInFriendTank ─> FriendGemFriendRouter

FriendGemFriendRouter (直通路由器)
    ├─ 序号超过 300 ──> FriendGemRosterLimit ──> 点击返回 ──> FriendGemDone
    ├─ 非好友文案 ──> FriendGemAddFriendPage ──> 点击返回 ──> FriendGemDone
    ├─ 欢迎弹窗 ──> FriendGemWelcomePopup (OCR「欢迎来到」点击关闭) ────┐
    ├─ 允许关闭的弹窗 ──> FriendGemSpecialPopup (绿勾且文案允许才点) ──┤
    ├─ 鱼宝乐园 ──> FriendGemFishBabyPark (OCR「鱼宝|乐园」点击右上X) ──┤
    │                                                                   │
    ├─ 遭遇海牛 ──> FriendGemCheckManatee ─> 共享海牛喂食 ─> 下一位 ───┼──┐
    │                                                                   │  │
    ├─ 体力耗尽 ──> FriendGemExhausted (OCR「刷新体力」/ 灰电) ────────┼──┤ (优先判断)
    │                                                                   │  │
    ├─ 快捷键可用 ─> 点击实际命中位置 ─> QuickCollectPostRouter ───────┼──┤
    │       ├─ 「刷新体力」可见 ─> QuickCollectExhausted ───────────────┤  │
    │       └─ 仍有剩余体力 ────> QuickCollectPartialDone ─────────────┤  │
    │           （两种结果均视为本好友处理完成，正常切下一位，           │  │
    │             不再回退气泡模式；剩余体力被接受为正常情况）           │  │
    ├─ 快捷键不可用/未识别 ─> FriendGemImageFallbackRouter              │  │
    │                                                                   │  │
    ├─ 发现气泡 ──> FriendGemCollectBubble (安全 ROI 模板匹配)          │  │
    │       ↓                                                           │  │
    │   FriendGemRecordAttempt (attempts + 1, miss_count 归零)          │  │
    │       │                                                           │  │
    │       └───────────────────────────────────────────────────────────┤  │
    │                                                                   │  │
    ├─ 连续无气泡 ─> FriendGemBubbleMissLimitReached (miss >= 12, ~7.2s) ┼──┤
    │                                                                   │  │
    ├─ 防死锁兜底 ─> FriendGemAttemptLimitReached (attempts >= 30 守护) ─┼──┤
    │                                                                   │  │
    └─ 单帧未见气泡 ─> FriendGemWaitForBubble (miss + 1, delay 600ms) ───┘  │
            │                                                              │
            └──────────────────────────────────────────────────────────────┘
    (海牛喂食完成、Exhausted、BubbleMissLimit 或 AttemptLimit 触发时)
    ↓
FriendGemNextFriend (模板匹配右上角「>」药丸按钮，点击切下一位)
    ↓
FriendGemStepIndex (friend_index + 1, miss_count 归零)
    ↓
FriendGemResetAttempts (attempts 清零，miss_count 清零)
    ↓
回到 FriendGemFriendRouter (巡访下一位好友)
```

---

## 核心设计决策与实机实测验证

### 1. 运行时状态解耦 (`agent/runtime_state.py`)
- 为避免 `my_action.py` 与 `my_reco.py` 之间的循环导入问题，专门设立轻量共享状态字典 `friend_gem_state`：
  ```python
  friend_gem_state = {
      "attempts": 0,
      "max_attempts": 30,  # 仅作极端防死锁安全兜底，不作为正常切好友条件
      "current_friend_index": 1,
      "bubble_miss_count": 0,
      "max_bubble_misses": 12,  # 允许连续未见气泡次数（约 7.2 秒），留足鱼群慢游缓冲
      "max_friend_index": 300,  # 好友序号全局上限；超过后结束任务，不再切下一位
      "roster_limit_logged": False,
  }
  ```
- `CheckFriendGemLimitReco` 仍只是单个好友的防死锁看门狗：达到 30 次尝试就切下一位，不会结束整趟好友摸宝。正常完成判断仍由 `刷新体力` 驱动。
- `CheckFriendGemRosterLimitReco` 在序号大于 300 时结束本轮。30 次上限不能挡住 2026-10-05 那种一直切陌生人的情况。初始化日志会同时写出「单个好友气泡尝试上限为 30」和「好友序号全局上限为 300」。

### 2. 状态驱动完成准则（State-Confirmed Completion）
- **核心原则**：绝不依赖点击次数判断好友是否摸完，彻底废除“点击满 12 次早退切人”的缺陷逻辑。
- **好友体力与耗尽标识（Exhausted）**：
  - 未清空状态：左侧显示黄色闪电和 `X 剩余`（如 `10 剩余`、`4 剩余`）；
  - 已清空状态：左侧显示灰色闪电和 `0(12点刷新体力)` 或 `0(0点刷新体力)`，包含稳定关键词 **`刷新体力`**；
  - **终态优先机制**：在 `FriendGemFriendRouter` 中，`FriendGemExhausted` 优先级高于气泡匹配；一旦出现 `刷新体力`，即使水中仍有残留小鱼气泡，也立即停止点击并安全切往下一位，零浪费操作。
  - **ROI 覆盖扩大**：检测区域定为 `[60, 200, 400, 160]`（$y=200 \sim 360$），完整兼容不同好友由于个人简介行数不同造成的文字垂直漂移。
  - **统一切好友状态链**：所有切好友分支（`FriendGemExhausted`、海牛喂食完成、`FriendGemBubbleMissLimitReached`、`FriendGemAttemptLimitReached`）统一汇聚至：
    $$\text{FriendGemNextFriend} \rightarrow \text{FriendGemStepIndex (StepFriendGemIndexAction)} \rightarrow \text{FriendGemResetAttempts (ResetFriendGemAttemptsAction)} \rightarrow \text{FriendGemFriendRouter}$$
    实现序号前进（`current_friend_index += 1`）与计数清零（`attempts = 0, bubble_miss_count = 0`）职责严格解耦。

### 3. 水族箱安全 ROI 防误触保护
- 水族箱内存在浮动 UI：左侧体力条与金币数、右侧菜单、底部状态。
- `FriendGemCollectBubble` 严格限制识别范围至水族箱中心开阔水域 **`ROI: [230, 140, 820, 470]`**。
- 实机全样本回测显示，中心水域金币气泡模板匹配得分均在 $0.95 \sim 0.98$ 之间，同时 100% 免疫左侧金币图标和顶部 HUD 的误匹配。

### 4. 气泡消失时延与去抖动
- 实机高速连拍验证（0.00s -> 0.25s -> 0.65s），点击后气泡消失时间 < 0.25 秒。
- `FriendGemCollectBubble` 点击后等待 500ms，保证气泡彻底离场并更新帧缓冲区，杜绝重复点击同一位置。
- 好友摸宝不适用主鱼缸“点击气泡后滑动鱼缸底部”的双倍奖励规则，保持原有点击与去抖流程。

### 5. 跨好友通用切换按钮
- 裁剪高精度特征模版 `assets/resource/image/好友_下一位.png`（橙色内药丸箭头）。
- 在右上角 `ROI: [1140, 50, 130, 80]` 内，无论 NPC、真人群体还是各种花哨背景，匹配置信度均稳定在 $0.76 \sim 0.98$。

### 6. 好友末尾与陌生人保护
- 遍历至最后一位星级好友后，再次点击 `>` 会进入加好友提示或陌生人水族箱。
- 2026-10-05 22:00 挂机「好友摸宝兜底」把序号从 1 加到 236。现场文案是「他还不是你的好友，无法进行操作哦~」「加他为好友么?」，绿色勾选约在 `[793,449,64,64]`。旧节点只在 `[750,330,160,70]` 找「全部添加」，全天没有命中；`FriendGemSpecialPopup` 只要看到绿色勾选就点击，于是发出了一次好友申请。申请发出后的「加好友邀请已经发出」也没有节点接管，装饰被当成气泡点了约 8.5 分钟。单个好友 30 次上限只会切到下一位，所以序号可以一直涨。上午 11:10 同路径曾到 112。
- `FriendGemAddFriendPage` 现在用宽 ROI `[250,140,820,400]` 识别「不是你的好友」「加他为好友」「加好友邀请已经发出」「去其他好友家看看吧」「全部添加」。命中后不点绿色勾选，只点左上角「返回」，再进入 `FriendGemDone`。`FriendGemFriendRouter` 与 `FriendGemImageFallbackRouter` 都把这条边界放在绿色勾选和气泡之前。
- 绿色勾选仍使用 `绿色勾选按钮.png`、ROI `[760,420,120,120]`、阈值 0.8，但必须同帧还有「谢谢您拜访」「些礼物」「进化鱼特效」或「已被关闭」。`FriendGemConfirmSafePopupAction` 在点击前再看一帧：出现加好友文案，或允许文案消失，就拒绝点击。拒绝后进入 `FriendGemSpecialPopupRefuse`，最多等 3 秒点左上角「返回」，再进 `FriendGemDone`；找不到返回时同样结束本轮。`FriendGemDone` 不和「返回」放在同一候选列表里，避免直接命中跳过返回。拜访礼物和「进化鱼特效已被关闭」仍可关闭。
- 序号大于 300 时 `FriendGemRosterLimit` 同样返回并结束。这个上限高于约 200 位好友的历史全表，用来挡住识别漏掉边界后的无限翻页。

### 7. 弹窗分层与长尾样本捕获
- **允许关闭的系统提示（`FriendGemSpecialPopup`）**：历史 E2E 在第 200 位见到「进化鱼特效已被关闭」。现在必须同时命中绿色勾选和允许文案，再由自定义动作点击勾选中心。加好友确认框不再被当成这类提示。
- **欢迎弹窗（`FriendGemWelcomePopup`）**：仍只认「欢迎来到」并点击该文字，不点击绿色勾选。

### 8. 误入鱼宝乐园自愈（`FriendGemFishBabyPark`）
- **误入场景**：在好友鱼缸采集气泡过程中，偶尔可能点击到底部右侧珊瑚/生物装饰，误进入好友的“鱼宝乐园”。
- **识别设计**：顶部标题艺术字检测，OCR `expected: "鱼宝|乐园"`，检测区域 `ROI: [380, 0, 520, 150]`（覆盖率 100%，正常水族箱零误报）。
- **恢复操作**：点击右上角固定黄色关闭按钮 `target: [1175, 25, 65, 60]`，延迟 1000ms 平滑返回原好友水族箱。
- **状态维护**：不重置 attempts，不增加 friend_index，不切好友，直通回到 `FriendGemFriendRouter` 继续摸宝。

### 9. 连续无气泡有界等待机制（`Bounded Miss Wait`）
- **有界等待架构**：
  - 运行时计数器 `bubble_miss_count` 上限提升至 `max_bubble_misses = 12`（约 7.2 秒）。
  - 单帧漏检进入 `FriendGemWaitForBubble`：`bubble_miss_count += 1`，等待 600ms 后重返 Router 重新检测气泡。
  - 只要任意一帧成功点击气泡（`RecordFriendGemAttemptAction`）或切好友（`ResetFriendGemAttemptsAction`），立即归零 `bubble_miss_count = 0`。
  - 仅当连续 12 次（约 7.2 秒）均无可用气泡时，命中 `FriendGemBubbleMissLimitReached`，才切下一位好友。为游动较慢的大型鱼或偏门鱼种预留充裕缓冲。

### 10. 多启动入口自适应（`FriendGemStartRouter`）
- **多入口支持**：
  - **入口 A（主鱼缸）**：`FriendGemOpenFriendPage` 在 `[1128,205,131,124]` 识别并点击 `好友页面_入口.png`，进入后重新路由。
  - **入口 B（好友列表）**：`FriendGemStartFromFriendList` 识别 `星级好友`，始终从首卡进入，避免为了先处理海牛而跳过排在它之前的普通好友；巡访到海牛页面后再由页面身份接管。
  - **入口 C1（直接在海牛页面启动）**：`FriendGemStartManateeTank` 识别顶部「海牛」，进入共享喂食流程。
  - **入口 C2（普通好友水族箱启动）**：`FriendGemStartInFriendTank` 识别 `剩余|刷新体力`，直通普通摸宝 Router。

### 11. 周末特殊好友【海牛先生】共享喂食
- **危险点**：左侧 `刷新体力` 区域可能包含付费刷新入口。流程只把该区域用于 OCR，所有喂食点击严格限制在用户指定的 `[792,288,341,355]`，不会点击付费刷新。
- **集成策略**：
  1. **好友列表层**：好友摸宝保持从第一位顺序巡访，不在列表中提前跳转海牛；独立海牛任务才使用 `[460,185,183,127]` 直接选择海牛先生；
  2. **巡访路由层**：`FriendGemCheckManatee` 命中后先由 `ManateeTankIdentity` 确认页面并检查是否已经刷新体力；未耗尽才进入 `ManateeOpenFeed -> ManateeSelectFood -> ManateeFeedUntilExhausted`；
  3. **完成恢复**：至少投喂 30 次后才开始接受 `刷新体力` 为终态；命中后走既有 `FriendGemNextFriend` 状态链继续后续好友；
  4. **安全熔断**：每次投喂前确认顶部 `海牛先生`，MFA 停止、截图失败、页面丢失或 120 次仍未出现终态时停止点击。

海牛独立任务、全部模板与完整返回分支见 `docs/features/manatee.md`。本轮只完成代码级验证，尚未进行周末 MFA 实测。

### 12. 好友摸宝快捷键优先与图像识别降级

2026-09-13 用户实测确认：在好友水族箱摇晃设备不会使宝石掉落。`FriendGemTask` 因此移除“收宝石方式”选项、`FriendGemSetGemCollectMode` 和 `FriendGemShakeGem` 分支。单缸收鱼和多鱼缸巡检的 IMAGE / SHAKE 选项保持不变。

普通好友鱼缸现按以下互斥状态处理：

1. 快捷按钮存在两个位置：常规好友在 ROI `[231,592,123,120]`，两个特殊好友在 ROI `[155,589,123,120]`（中心对齐用户实测点 [205,639,23,21]，两处 ROI 同尺寸）。`FriendGemRouter` 候选依次评估 `FriendGemQuickCollectAvailable`（主位置）→ `FriendGemQuickCollectAvailableAlt`（第二位置），任一命中即点击模板实际位置，等待页面稳定（post_delay 2000）后由 `FriendGemQuickCollectPostRouter` 按真实页面正常分流：
   - OCR 识别到「刷新体力」→ `FriendGemQuickCollectExhausted`：快捷摸宝完成且体力已耗尽，切换下一位；
   - 未识别到「刷新体力」→ `FriendGemQuickCollectPartialDone`（DirectHit 正常命中，不产生 error）：快捷摸宝已一次收走当前可收宝石，剩余体力是正常情况（可收宝石可能少于剩余体力），按策略接受少量体力浪费，直接切换下一位。
2. **快捷摸宝成功点击后，本好友处理即告结束**：当前好友内绝不再进入 `FriendGemImageFallbackRouter` / `FriendGemCollectBubble` / `FriendGemWaitForBubble`（旧 `FriendGemQuickCollectVerifyExhausted` on_error → `VerifyFallback` 降级链已删除）。
3. 若命中同 ROI 的 `好友摸宝快捷键_不可用.png`，立即转入 `FriendGemImageFallbackRouter`，沿用 `金币气泡.png` 逐个识别点击流程。
4. 一旦本好友进入图像识别降级路径，收取及等待循环不再反复检测快捷键；切换下一位好友后才重新判断快捷键状态。
5. 两个快捷键模板仅接入 `FriendGemTask`。`SeaOtterGemTask` 不引用它们，仍只允许点击左下角海獭执行摸宝。

2026-09-18 快捷摸宝后语义修正：不再强求体力耗尽，未耗尽也正常切下一位（纯 Pipeline 修改，Agent 逻辑未动）。专项测试 `dev/test_friend_gem.py`（Case 1~5 + 静态可达性契约）全部通过；代码级验证完成，待实机复测。

---

## 44 分钟全量 E2E 实测指标 (2026-09-02)

| 统计指标 | 观测数据 | 结论 |
| :--- | :--- | :--- |
| **总访问水族箱/好友数** | 200 个 | 全链路畅通 |
| **正常采集好友数** | 198 位 | 自动采集 2~12 颗气泡 |
| **体力耗尽跳过好友数** | 2 位 | 识别“刷新体力”灰电 0 点击直通切换 |
| **气泡匹配置信度** | 0.7658 ~ 0.9845 | 开阔水域安全 ROI 杜绝任何 UI 误触 |
| **切好友按钮置信度** | 0.7510 ~ 1.0000 | 跨背景 100% 成功切换，无漏判跳号 |
| **卡死与未知稳定异常** | 0 次 | 稳健性达到端到端收敛标准 |
| **金币收益** | +597,637 金币 | 自动化成效显著 |
| **连续运行总耗时** | 2645.3 秒 (44.1 分钟) | 无人工干预长程巡检验证通过 |
