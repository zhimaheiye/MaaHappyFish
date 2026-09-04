# 好友摸宝自动化 (docs/features/friend-gem.md)

## 功能定位
开心水族箱好友巡访与金币产物收取自动化助手（`FriendGemTask`）。自动从星级好友列表第一位开始，依次进入好友水族箱采集金币气泡；单好友最多尝试 12 次点击，体力耗尽（灰电/0点刷新体力）自动跳过，支持遇到加好友/陌生人推荐页面时平滑收敛结束。

## ⚠️ 任务启动前置条件（重要）
- **必须在「我的星级好友」列表页面顶部开始任务**（顶部第 3 个 Tab，确保第 1 排好友卡片可见）。
- 脚本自动点击首位好友卡片进入，并在好友之间通过右上角「下一位 (`>`)」药丸按钮连续巡访。

---

## 状态机流转设计

```text
FriendGemTask (入口，InitFriendGemStateAction 初始化状态)
    ↓
FriendGemStartRouter (启动环境自适应路由器)
    ├─ 位于好友列表 ──> FriendGemStartFromFriendList (OCR「星级好友」) ──> 点击首卡 ─┐
    └─ 位于好友鱼缸 ──> FriendGemStartInFriendTank (OCR「剩余|刷新体力」) ─> DoNothing ──┤
                                                                                        │
                                                                                        ▼
FriendGemFriendRouter (直通路由器)
    ├─ 到达末尾 ──> FriendGemAddFriendPage (OCR「全部添加」/ 无状态栏) ──> FriendGemDone (结束)
    ├─ 欢迎弹窗 ──> FriendGemWelcomePopup (OCR「欢迎来到」点击关闭) ────┐
    ├─ 系统弹窗 ──> FriendGemSpecialPopup (匹配「绿色勾选按钮.png」) ───┤
    ├─ 鱼宝乐园 ──> FriendGemFishBabyPark (OCR「鱼宝|乐园」点击右上X) ──┤
    │                                                                   │
    ├─ 体力耗尽 ──> FriendGemExhausted (OCR「刷新体力」/ 灰电) ────────┐  │
    ├─ 次数已满 ──> FriendGemAttemptLimitReached (CheckFriendGemLimit) │  │
    │                                                                   │  │
    ├─ 发现气泡 ──> FriendGemCollectBubble (安全 ROI 模板匹配)          │  │
    │       ↓                                                           │  │
    │   FriendGemRecordAttempt (attempts + 1, miss_count 归零)          │  │
    │       │                                                           │  │
    │       └───────────────────────────────────────────────────────────┤  │
    │                                                                   │  │
    ├─ 连续无气泡兜底 ─> FriendGemBubbleMissLimitReached (miss >= 8) ───┤  │
    │                                                                   │  │
    └─ 单帧未发现气泡 ─> FriendGemWaitForBubble (miss + 1, delay 600ms) │  │
            │                                                           │  │
            └───────────────────────────────────────────────────────────┤  │
                                                                        ▼  ▼
                                                              FriendGemFriendRouter
    (仅当 Exhausted、AttemptLimitReached 或 BubbleMissLimitReached 时)
    ↓
FriendGemNextFriend (模板匹配右上角「>」药丸按钮，点击切下一位)
    ↓
FriendGemResetAttempts (attempts 清零，miss_count 清零，friend_index + 1)
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
      "max_attempts": 12,
      "current_friend_index": 1,
  }
  ```
- 保证 `CheckFriendGemLimitReco` 仅做纯判断（返回 `(0, 0, 10, 10)` 或 `None`），不产生自增副作用；自增由动作节点 `RecordFriendGemAttemptAction` 显式驱动。

### 2. 局部体力与全局终态解耦
- **好友体力（Friend-local Quota）**：实测确认好友头顶的 `X 剩余` 为单好友可摸上限（通常为 10 或 12），不是每日全局上限。
- **耗尽标识（Exhausted）**：当某好友今日已被摸完，会显示 `0(0点刷新体力)` 或 `0(12点刷新体力)` 并伴随灰色闪电。
  - **ROI 扩大**：检测区域定为 `[60, 210, 400, 140]`（覆盖 $x=60 \sim 460$），防止旧版因右边界 $x=320$ 将字符串末尾的“力”字符截断导致漏防。
  - **直通下一位（DoNothing 与稳定性经验）**：耗尽的业务判断已完全由 OCR 识别“刷新体力”承担，动作采用 `DoNothing` 直通 `FriendGemNextFriend`。**核心经验**：观测/日志逻辑不应成为关键业务流的必经 CustomAction，除非该 Action 本身承担必要状态变更；避免日志回调异常阻断核心导航。
  - **统一切好友状态链**：所有切好友分支（`FriendGemExhausted`、`FriendGemAttemptLimitReached`、`FriendGemBubbleMissLimitReached`）统一汇聚至：
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
- **根因缺陷修复**：原 `FriendGemFriendRouter` 末尾将 `FriendGemNextFriend` 作为默认 fallback。因右上方「>」按钮始终存在，一旦某帧产物气泡因游动遮挡暂时未被命中，即误切离开当前好友（引发“剩9体力就跳下一位”现象）。
- **有界等待架构**：
  - 彻底从 `FriendGemFriendRouter.next` 中剔除 `FriendGemNextFriend`。
  - 新增运行时计数器 `bubble_miss_count`（上限 `max_bubble_misses = 8`）。
  - 单帧漏检进入 `FriendGemWaitForBubble`：`bubble_miss_count += 1`，等待 600ms 后重返 Router 重新检测气泡。
  - 只要任意一帧成功点击气泡（`RecordFriendGemAttemptAction`）或切好友（`ResetFriendGemAttemptsAction`），立即归零 `bubble_miss_count = 0`。
  - 仅当连续 8 次（约 4.8 秒）均无可用气泡时，命中 `FriendGemBubbleMissLimitReached`，才受控切下一位好友。

### 10. 双启动入口自适应（`FriendGemStartRouter`）
- **双启动支持需求**：
  - **入口 A（好友列表主界面）**：识别顶部 `ROI: [110, 100, 200, 55]` 标题 `星级好友`，点击首卡进入第 1 位好友。
  - **入口 B（任意好友水族箱）**：识别左侧状态区 `ROI: [60, 210, 400, 140]` 状态文字 `剩余|刷新体力`，动作 `DoNothing` 直通 Router，直接把当前鱼缸作为巡访起点，绝不返回列表，绝不在鱼缸内误点首卡区域 `[120, 320]`，绝不提前跳号。
- **巡访序号语义澄清**：`current_friend_index` 明确代表“本次任务从启动点算起的巡访序号”（在任意好友水族箱启动时，该鱼缸即为本轮第 1 位好友），不再假定为好友列表的绝对全局排名。

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