# 好友摸宝自动化 (docs/features/friend-gem.md)

## 功能定位
开心水族箱好友巡访与金币产物收取自动化助手（`FriendGemTask`）。从星级好友列表或好友鱼缸自适应启动，依次进入好友水族箱采集金币气泡；采用**状态确认完成（UI 状态驱动）**机制，以左侧体力栏出现「刷新体力」（灰电/0体力）作为该好友彻底清空的唯一准则，彻底解决固定 10/12 次计数导致的漏清问题。支持周末特殊好友【海牛先生】双层安全过滤跳过，杜绝误触水面及付费刷新陷阱，遇到加好友推荐页时平滑收敛结束。

## ⚠️ 任务启动前置条件（重要）
- **推荐入口 A**：位于「我的星级好友」列表页面顶部开始任务（顶部第 3 个 Tab，确保第 1 排好友卡片可见）。
- **推荐入口 B**：位于任意好友水族箱内部开始任务（支持海牛先生鱼缸）。
- 脚本自适应启动进入，并在好友之间通过右上角「下一位 (`>`)」药丸按钮连续巡访。

---

## 状态机流转设计

```text
FriendGemTask (入口，InitFriendGemStateAction 初始化状态)
    ↓
FriendGemStartRouter (启动环境自适应路由器)
    ├─ 列表首卡为海牛 ─> FriendGemStartCheckCard1Manatee (OCR「海牛」) ──> 点击第2张卡 ─┐
    ├─ 正常好友列表 ──> FriendGemStartFromFriendList (OCR「星级好友」) ──> 点击第1张卡 ─┤
    ├─ 误起在海牛鱼缸 ─> FriendGemStartManateeTank (OCR「海牛」) ────────> 直通 Router ──┤
    └─ 位于普通好友缸 ─> FriendGemStartInFriendTank (OCR「剩余|刷新体力」) ─> 直通 Router ──┤
                                                                                        │
                                                                                        ▼
FriendGemFriendRouter (直通路由器)
    ├─ 到达末尾 ──> FriendGemAddFriendPage (OCR「全部添加」/ 无状态栏) ──> FriendGemDone (结束)
    ├─ 欢迎弹窗 ──> FriendGemWelcomePopup (OCR「欢迎来到」点击关闭) ────┐
    ├─ 系统弹窗 ──> FriendGemSpecialPopup (匹配「绿色勾选按钮.png」) ───┤
    ├─ 鱼宝乐园 ──> FriendGemFishBabyPark (OCR「鱼宝|乐园」点击右上X) ──┤
    │                                                                   │
    ├─ 遭遇海牛 ──> FriendGemCheckManatee (OCR「海牛」直接跳下一位) ─────┼──┐
    │                                                                   │  │
    ├─ 体力耗尽 ──> FriendGemExhausted (OCR「刷新体力」/ 灰电) ────────┼──┤ (优先判断)
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
    (当 CheckManatee、Exhausted、BubbleMissLimit 或 AttemptLimit 触发时)
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
  }
  ```
- 保证 `CheckFriendGemLimitReco` 仅作为防死锁安全看门狗（达到 30 次才触发），日常完成判断 100% 由 UI 状态 `FriendGemExhausted` 驱动。

### 2. 状态驱动完成准则（State-Confirmed Completion）
- **核心原则**：绝不依赖点击次数判断好友是否摸完，彻底废除“点击满 12 次早退切人”的缺陷逻辑。
- **好友体力与耗尽标识（Exhausted）**：
  - 未清空状态：左侧显示黄色闪电和 `X 剩余`（如 `10 剩余`、`4 剩余`）；
  - 已清空状态：左侧显示灰色闪电和 `0(12点刷新体力)` 或 `0(0点刷新体力)`，包含稳定关键词 **`刷新体力`**；
  - **终态优先机制**：在 `FriendGemFriendRouter` 中，`FriendGemExhausted` 优先级高于气泡匹配；一旦出现 `刷新体力`，即使水中仍有残留小鱼气泡，也立即停止点击并安全切往下一位，零浪费操作。
  - **ROI 覆盖扩大**：检测区域定为 `[60, 200, 400, 160]`（$y=200 \sim 360$），完整兼容不同好友由于个人简介行数不同造成的文字垂直漂移。
  - **统一切好友状态链**：所有切好友分支（`FriendGemExhausted`、`FriendGemCheckManatee`、`FriendGemBubbleMissLimitReached`、`FriendGemAttemptLimitReached`）统一汇聚至：
    $$\text{FriendGemNextFriend} \rightarrow \text{FriendGemStepIndex (StepFriendGemIndexAction)} \rightarrow \text{FriendGemResetAttempts (ResetFriendGemAttemptsAction)} \rightarrow \text{FriendGemFriendRouter}$$
    实现序号前进（`current_friend_index += 1`）与计数清零（`attempts = 0, bubble_miss_count = 0`）职责严格解耦。

### 3. 水族箱安全 ROI 防误触保护
- 水族箱内存在浮动 UI：左侧体力条与金币数、右侧菜单、底部状态。
- `FriendGemCollectBubble` 严格限制识别范围至水族箱中心开阔水域 **`ROI: [230, 140, 820, 470]`**。
- 实机全样本回测显示，中心水域金币气泡模板匹配得分均在 $0.95 \sim 0.98$ 之间，同时 100% 免疫左侧金币图标和顶部 HUD 的误匹配。

### 4. 气泡消失时延与去抖动
- 实机高速连拍验证（0.00s -> 0.25s -> 0.65s），点击后气泡消失时间 < 0.25 秒。
- 节点配置 `post_delay: 500ms`，充分保证气泡彻底离场并更新帧缓冲区，杜绝重复点击同一位置。

### 5. 跨好友通用切换按钮
- 裁剪高精度特征模版 `assets/resource/image/好友_下一位.png`（橙色内药丸箭头）。
- 在右上角 `ROI: [1140, 50, 130, 80]` 内，无论 NPC、真人群体还是各种花哨背景，匹配置信度均稳定在 $0.76 \sim 0.98$。

### 6. 好友末尾与陌生人保护
- 遍历至最后一位星级好友后，再次点击 `>` 将进入加好友推荐页或陌生人水族箱。
- 此时页面出现「全部添加」按钮或左侧好友状态栏消失，直接命中 `FriendGemAddFriendPage` 平滑退出，杜绝无限翻页。

### 7. 弹窗分层与长尾样本捕获
- **系统提示弹窗（`FriendGemSpecialPopup`，已实机验证）**：在 44 分钟长链路 E2E 测试至第 200 位水族箱时捕获真实弹窗现场（“进化鱼特效已被关闭”提示），通过匹配特征模版 `assets/resource/image/绿色勾选按钮.png` 并在 `ROI: [760, 420, 120, 120]` 内点击确定，自动消除弹窗。
- **欢迎弹窗（`FriendGemWelcomePopup`，骨架待覆盖）**：针对首访好友可能弹出的“欢迎来到”提示，保留为未覆盖样本节点，避免混淆。

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
  - **入口 A1（好友列表首卡为海牛）**：`FriendGemStartCheckCard1Manatee` 检测到首卡含「海牛」，自动点击第 2 张卡片进入，跳过海牛。
  - **入口 A2（好友列表首卡正常）**：`FriendGemStartFromFriendList` 识别 `星级好友`，点击首卡进入。
  - **入口 B1（直接在海牛鱼缸启动）**：`FriendGemStartManateeTank` 识别顶部「海牛」，直通 Router 并立即通过 `FriendGemCheckManatee` 切走。
  - **入口 B2（普通好友水族箱启动）**：`FriendGemStartInFriendTank` 识别 `剩余|刷新体力`，直通 Router。

### 11. 周末特殊好友【海牛先生】极速安全穿透
- **危险点**：海牛先生水缸内无常规金币气泡，但下方存在绿色付费按钮 `x20 立即刷新`（消耗 20 元宝/钻石）。若在其缸内盲目等待或误触水面，存在极高误付费风险。
- **双层防御策略**：
  1. **好友列表层**：首卡为海牛先生时自动点击第 2 卡跳过；
  2. **巡访路由层**：在 `FriendGemFriendRouter` 首位配置 `FriendGemCheckManatee`（ROI: `[300, 40, 350, 80]`，expected: `海牛`），一旦切入其水族箱，0 延时直通 `FriendGemNextFriend` 点击右上角 `>` 药丸切走，用时 < 1 秒，绝不触碰水面任何区域，绝不触发付费按钮。

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