# 开贝壳活动自动化 (docs/features/open-shell.md)

## 功能定位
开心水族箱限时/常驻活动“大章鱼开贝壳”自动化小助手。支持从主鱼缸识别活动入口或从活动主页直接开始，用户可设定连续执行次数 $N$；普通奖励始终选择继续开贝壳，遇章鱼固定保留一个随机奖品，完成后自动返回并确认主鱼缸。

## Start Contract

- 已在大章鱼活动主页：优先在 `[37,68,226,142]` 用 `开贝壳_识别.png` 确认页面，直接进入“立即开始”流程。
- 位于主鱼缸且活动入口可见：在 `[289,492,168,139]` 匹配 `开贝壳_入口.png` 并点击，随后在 `[271,573,101,45]` OCR 识别并点击“进入”，再由 `[37,68,226,142]` 的 `开贝壳_识别.png` 新页面门禁确认成功进入大章鱼主页。
- `开贝壳_误触识别.png`（ROI `[498,80,280,191]`）只表示点击主鱼缸贝壳后出现的第一层入口页：独立开贝壳任务在该层继续 OCR 点击“进入”，收鱼/巡检误触恢复则 OCR 点击左上角“返回”；该模板不替代第二层大章鱼主页门禁。
- 其他未知页面：不使用固定坐标兜底，记录页面门禁失败并安全停止。

---

## 状态机流转设计

```text
OpenShellTask / GreenWildDailyTask
    ↓ (统一启动路由 OpenShellStartRouter，候选按序)
    ├─ 已在活动主页 ─────────────> OpenShellStartPage (门禁确认)
    ├─ 已在贝壳分类页 ───────────> OpenShellCategoryPage (门禁确认)
    ├─ 主鱼缸且入口可见 ─> OpenShellEntry (识别并点击贝壳入口)
    ├─ 主鱼缸但入口暂时不可见（被鱼挡）─> OpenShellRetryEntryFromMainTank
    │       （主界面特征门禁 + 700ms 等待 → 回 StartRouter 重新截图识别，无小上限）
    └─ 未知页面 ─> OpenShellAbort (安全停止)
                                      ↓
                        （点击后按真实页面分流，兼容游鱼遮挡点击未生效）
                          ├─ 已进贝壳分类页 ─> OpenShellCategoryPage ─> OpenShellEnter
                          ├─ 仍在主鱼缸（被鱼挡住）─> OpenShellEntryRetryOnMainTank
                          │                                ─> OpenShellEntryRetryGate
                          │                                ─> 回到 OpenShellEntry 重新识别点击
                          └─ 其它未知页面 ─────> OpenShellAbort (安全停止)
    ↓
OpenShellRoundStart (点击「立即开始」)
    ↓
OpenShellOpenFirst (点击「打开贝壳」)
    ↓
OpenShellResultRouter (直通路由器)
    ├─ 遇章鱼 ──> OpenShellOctopus (点击「保留一个随机奖品」) ──> OpenShellFinish
    ├─ 五贝开完 ─────────────────────────────────────────────> OpenShellFinish
    └─ 普通奖励 ─> OpenShellContinue (点击「继续开贝壳」) ───┐
                                                            │ (循环)
                                                            ▼
                                                   OpenShellResultRouter
    ↓
OpenShellFinish (点击「太好了」)
    ↓
OpenShellConfirmReturn (OCR 识别「立即开始」，DoNothing 确认回到 A)
    ↓
OpenShellLoopRouter (循环路由器)
    ├─ 轮次未满 (< N) ──> OpenShellShouldContinue ──> 回到 OpenShellRoundStart (下一轮)
    └─ 轮次已达 (>= N) ─> OpenShellDone (OCR 点击左上角“返回”)
                                      ↓
                        （第一次返回后的页面分流，兼容两种真实页面栈）
                          ├─ 已直达主鱼缸 ──> OpenShellVerifyMainAfterDone (确认主鱼缸后完成)
                          └─ 仍在贝壳分类页 ──> OpenShellReturnFromCategory (第二次返回)
                                                      ↓
                                       OpenShellVerifyMainAfterDone (确认主鱼缸后完成)
                                      ↓
                          GreenWildDailyBuyFishEntry（仅绿野寻仙踪日常待买鱼时）
                          OpenShellStandaloneComplete（独立开贝壳到此结束）
```

---

## 核心设计决策与容错保障

### 0. 页面门禁与返回动作

- `开贝壳_识别.png` 是用户提供的大章鱼页面本体稳定识别模板，识别 ROI 为 `[37,68,226,142]`。独立 `OpenShellTask` 必须先命中该门禁，才进入「立即开始」OCR 流程。该页面门禁同时被以下三处共享：
  - `OpenShell`（独立开贝壳任务入口与主页门禁）
  - `CollectFish`（挂机收鱼误入恢复 `HandleShellPage`）
  - `Patrol`（多鱼缸巡检误入恢复 `PatrolShellPagePopup`）
- `开贝壳_入口.png` 是用户提供的主鱼缸活动入口模板，ROI 为 `[289,492,168,139]`；命中后点击实际识别位置，随后确认第一层分类页 `开贝壳_误触识别.png`，再在左侧 `[160,500,280,140]` OCR 点击普通贝壳「进入」。点不进大章鱼页时点击分类页「返回」回到鱼缸，不把人停在分类页。
- `开贝壳_误触识别.png` 是上述点击后的第一层入口页门禁，ROI 为 `[498,80,280,191]`。它供收鱼和巡检判断“从鱼缸误触进入”并安全返回，同时作为独立功能“兑换金贝壳券”(`GoldShellCouponTask`) 在第一层贝壳分类页的页面门禁；它不替代第二层大章鱼主页门禁。
- `贝壳页面_返回.png` 只截取左上角返回按钮，ROI 为 `[0,0,250,150]`，只能在页面本体门禁通过后用于识别点击，不能单独证明当前是大章鱼页面。2026-09-12 报告已确认鱼缸管理页存在同款按钮并可达到 0.999998 的错误匹配；巡检与收鱼流程现均遵守这套两阶段门禁。
- 其他任务处理误入大章鱼页面时应复用“页面本体门禁 -> 返回按钮点击”的两段契约，不得改用 `活动页面_退出.png` 通用活动页模板。多鱼缸巡检通过 `[JumpBack]PatrolShellPagePopup` 接入该流程。
- 独立任务达到设定次数时，前序 `OpenShellConfirmReturn` 已用“立即开始”确认活动主页；随后在 `[0,0,173,123]` OCR 识别并点击“返回”，最后用 `主界面特征.png` 确认已经回到鱼缸。返回 OCR 或主鱼缸门禁失败都会安全停止。
- **入口点击后必须以页面门禁判定成功，Click Succeeded 只代表点击发出**：鱼缸里的鱼会游动，可能出现“入口模板识别成功、点击瞬间被鱼挡住、页面仍停在主鱼缸”的情况。`OpenShellEntry` 的 next 依次评估 `OpenShellCategoryPage`（分类页确认，成功标准）→ `OpenShellEntryRetryOnMainTank`（`主界面特征.png` `[0,200,150,400]` 命中＝确认仍在主鱼缸，DoNothing 绝不下发点击）→ `OpenShellEnter`（分类页 OCR 兜底，原有语义保持）。确认仍在主鱼缸时经 `OpenShellEntryRetryGate`（`CheckOpenShellEntryRetryReco`，task_id 隔离计数，默认宽松上限 15 次）回到 `OpenShellEntry` 重新截图、重新模板识别、用最新 bbox 重新点击；禁止重复点击旧坐标，未知页面不重试、直接安全停止。不降 threshold、不扩 ROI、不使用固定坐标。
- **完成后的退出按页面分流，不假设一次返回必达主鱼缸**：真实页面栈是 `大章鱼开贝壳页（第二层）→ 返回 → 贝壳分类页（第一层）→ 再返回 → 主鱼缸`。2026-09-18 实机日志与失败帧离线匹配（`开贝壳_误触识别.png` = 1.0000 HIT，`主界面特征.png` = 0.357 MISS）证实第一次返回只退到分类页。因此 `OpenShellDone` 的 next 为 `[OpenShellVerifyMainAfterDone, OpenShellReturnFromCategory]`：已直达主鱼缸时 VerifyMain 直接命中、不产生多余点击；仍在分类页时复用现有 `OpenShellReturnFromCategory` 再点一次返回，回到同一 VerifyMain。分类页门禁节点 `OpenShellCategoryPage` 的业务方向是再次进入大章鱼页（`OpenShellEnter`），不得复用到退出路由。

### 1. 轮次计数的严格业务定义
- “1 次”的定义**不是**指开单个贝壳，而是指：
  `大章鱼主页「立即开始」 -> 开贝壳 -> 循环/结算 -> 「太好了」 -> 重新看到大章鱼主页「立即开始」`。
- 在 `OpenShellConfirmReturn` 只做识别不点击，进入 `CheckOpenShellLoopReco` 判定。只有此时计数才 $+1$。
- 利用 `task_id` 自动隔离不同任务运行，任务停止重启后计数自动重置为 0。

### 2. OCR 分词抵抗设计
- 实机测试中，底部按钮“保留一个随机奖品”容易因字间距被 PP-OCR 拆分成 `[保留]` 和 `[一个随机奖品]` 两个独立的检测框。
- `OpenShellOctopus` 采用 **`"expected": "随机奖品"`**，不论 OCR 合并还是拆分均能稳定命中，点击中心落在按钮安全区域，杜绝超时假死。

### 3. 多视觉变体（Variants）兼容
- 结算界面存在两种布局：
  - **变体 1（章鱼后结算）**：居中单个黄色「太好了」按钮（$x \approx 505$）。
  - **变体 2（五贝全开结算）**：左侧绿色「分享」+ 右侧偏右黄色「太好了」按钮（$x \approx 720$）。
- `OpenShellFinish` 统一采用大跨度 ROI `[400, 550, 650, 160]`，横向覆盖 $x: 400 \sim 1050$，一网打尽所有结算变体。

## 当前验证状态

- 2026-09-13 导航与门禁定向优化：补齐主鱼缸入口到大章鱼主页之间的“进入”步骤（`OpenShellEnter`，ROI `[271,573,101,45]`，OCR 匹配 `^进入$`）；同时更换大章鱼页面门禁为用户提供的稳定模板 `开贝壳_识别.png`，ROI 同步更新为 `[37,68,226,142]`（OpenShell、CollectFish 与 Patrol 三处共享）。静态契约测试、Pipeline 正则与资源加载、Agent 引用门禁全部通过，代码级验证完成，本次未做模拟器测试。
- 2026-09-14 恢复第一层入口页的独立模板语义：`开贝壳_误触识别.png` 仅用于收鱼/巡检误触返回，`开贝壳_识别.png` 继续只识别第二层大章鱼主页；本次未改独立开贝壳任务的正常“进入”流程。
- 2026-09-18 修复完成后退出层级假设错误：日常收尾（绿野寻仙踪日常）实机完成 1/1 轮开贝壳后，`OpenShellDone` 点击一次返回实际只退到贝壳分类页，`OpenShellVerifyMainAfterDone` 连续 5 次识别主鱼缸失败后 `OpenShellAbort` 的 StopTask 终止了整个 DailyRoutineTask。修复为第一次返回后按页面分流（主鱼缸直达 / 分类页二次返回），`dev/test_open_shell_exit.py` 覆盖两级返回、直达主鱼缸、GreenWildDaily 续接买鱼、Standalone 不被残留标记劫持 4 个语义场景；代码级验证通过。
- 2026-09-19 启动阶段入口遮挡重试：实机日志（00:11 日常收尾）证实 GreenWildDailyTask 启动开贝壳时 `OpenShellEntry` 模板单帧 miss（游鱼瞬时遮挡）即被候选链末尾的 DirectHit Abort 终止。抽出统一 `OpenShellStartRouter`（StartPage > CategoryPage > Entry > RetryEntryFromMainTank > Abort），新增 `OpenShellRetryEntryFromMainTank`（`主界面特征.png` 门禁 + 700ms 等待 → 回 Router 重新截图识别，无小上限，Stop 正常停止）；`OpenShellTask` 与 `GreenWildDailyTask` 均收敛到该 Router，移除"前三个候选单帧 miss → 立即 Abort"语义。模板/threshold/ROI 与已完成的两级退出均未动。`dev/test_open_shell_exit.py` 新增启动重试 5 场景（首帧 miss、连续 3 帧被挡、分类页/大章鱼页直启、未知页 Abort、双入口一致性）全部通过；代码级验证完成，待实机复测。
- 2026-09-18 修复入口被游动鱼遮挡导致 Abort：用户实机确认点击入口瞬间被鱼挡住时页面仍停主鱼缸并走失败。`OpenShellEntry` 点击后增加页面分流——命中分类页正常继续；`主界面特征.png` 确认仍在主鱼缸则经 `OpenShellEntryRetryOnMainTank`（DoNothing 门禁 + 500ms 等待）与 `OpenShellEntryRetryGate`（`CheckOpenShellEntryRetryReco` 计数，宽松上限 15、task_id 隔离、带编号日志）回到 `OpenShellEntry` 重新识别点击，每次重试重新截图取最新 bbox；未知页面不重试直接安全停止。模板/threshold/ROI 未动。`dev/test_open_shell_exit.py` 新增 E1~E6 语义场景（一次成功、挡一次重试、连挡 3 次、永久被挡熔断、未知页面安全失败、task_id 归零）全部通过；代码级验证完成，待实机复测。已知独立问题：`OpenShellAbort` 的 StopTask 在日常收尾串联场景会终止父任务，属“子任务 StopTask 会停掉整段挂机”同类事项，维持 ISSUES.md 已有记录，本轮未重构。
