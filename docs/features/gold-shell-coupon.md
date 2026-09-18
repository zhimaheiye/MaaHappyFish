# 兑换金贝壳券自动化 (docs/features/gold-shell-coupon.md)

## 一、功能定位

“兑换金贝壳券”(`GoldShellCouponTask`) 是开心水族箱贝壳体系下的常驻自动化子功能。支持从主鱼缸识别贝壳分类入口、从贝壳分类页就地启动，进入金贝壳页面后检查右上角“兑换”按钮，完成金贝壳券兑换；点击兑换后必须经过兑换后状态验证（按钮消失或结算弹窗）；若经多次复核无可兑换或今日已兑换，则作为正常完成分支退出；随后通过两级状态驱动返回安全回到主鱼缸。

> 金贝壳主页使用用户提供的 `金贝壳_识别.png`（ROI `[515, 360, 232, 195]`）作为正向门禁。仅有左上角返回按钮不能当作金贝壳主页，避免海星宠物页误判。

该功能既可作为独立任务（`GoldShellCouponTask`）运行，也可作为子任务接入【日常收尾】(`DailyRoutineTask`) 串行容器。

---

## 二、Start Contract (步骤可恢复设计)

严格遵守“当前真实截屏判定阶段”与安全降级原则：

```text
GoldShellCouponTask -> GoldShellCouponRouter
                         ├─ 阶段 3: 已在金贝壳主页 (GoldShellCouponVerifyGoldPage / 金贝壳_识别.png)
                         ├─ 阶段 2: 已在贝壳分类页 (GoldShellCouponVerifyCategoryPage) -> 点击进入金贝壳
                         ├─ 阶段 1: 处于主鱼缸 (GoldShellCouponEntry) -> 点击贝壳入口
                         ├─ 误入海星宠物页 (萌/乖/亮海星) -> 点击返回后重新走 Router
                         └─ 未知状态 -> GoldShellCouponAbort (安全停止，严禁盲点)
```

- **阶段 3（金贝壳主页）**：命中 `金贝壳_识别.png`（ROI `[515, 360, 232, 195]`）后直接检查兑换按钮。
- **阶段 2（贝壳分类页）**：命中顶部 `开贝壳_误触识别.png`（ROI `[498, 80, 280, 191]`），在 `[904, 579, 108, 40]` OCR 识别点击右侧“进入”按钮。
- **阶段 1（主鱼缸）**：命中 `开贝壳_入口.png`（ROI `[289, 492, 168, 139]`），点击进入分类页。
- **误入海星宠物页**：顶部 OCR `[萌乖亮]海星` 后点击左上角“返回”，再从 Router 重试。
- **未识别到兑换 / 误入开贝壳大章鱼页**：点击左上角返回两次回到鱼缸，经双出口继续日常收尾，不报错停止。

---

## 三、状态机流转与核心契约

```mermaid
flowchart TD
    Task[GoldShellCouponTask] --> Router{GoldShellCouponRouter 步骤恢复}
    
    Router -- 阶段3: 已在金贝壳主页 --> VerifyGold[GoldShellCouponVerifyGoldPage]
    Router -- 阶段2: 已在分类页 --> VerifyCat[GoldShellCouponVerifyCategoryPage]
    Router -- 阶段1: 在主鱼缸 --> Entry[GoldShellCouponEntry: 点击开贝壳_入口.png]
    Router -- 误入海星宠物页 --> Starfish[GoldShellCouponStarfishMisTouch -> 返回 -> Router]
    Router -- 未知状态 --> Abort[GoldShellCouponAbort: 安全停止]

    %% 阶段1 -> 阶段2
    Entry --> VerifyCat

    %% 阶段2 -> 阶段3
    VerifyCat --> EnterGold[GoldShellCouponEnterGold: [904,579,108,40] OCR ^进入$ 并点击]
    EnterGold --> VerifyGold[GoldShellCouponVerifyGoldPage: CheckGoldShellPageReco 专属门禁]

    %% 阶段3 兑换逻辑
    VerifyGold --> CheckExchange{GoldShellCouponCheckExchange: [1136,41,91,35] OCR ^[兑兌][换換]$}
    
    CheckExchange -- 命中兑换 --> DoExchange[GoldShellCouponCheckExchange: 点击兑换]
    DoExchange --> PostRouter{GoldShellCouponPostExchangeRouter 状态验证}
    
    PostRouter -- 优先: 消耗确认对号弹窗 --> ConfirmPopup[GoldShellCouponConfirmPopup: 点击绿色勾选]
    ConfirmPopup --> PostConfirm[GoldShellCouponPostConfirmRouter]

    PostRouter -- 结算: 太好了 --> GreatBtn[GoldShellCouponGreatButton: [568,512,153,51] OCR 点击太好了]
    PostConfirm -- 结算: 太好了 --> GreatBtn
    GreatBtn --> ReturnCat[GoldShellCouponReturnCategory: 点击左上角返回]

    PostRouter -- 方案B: 出现获得/结算弹窗 --> RewardPopup[GoldShellCouponRewardPopup: 点击确定关闭]
    PostConfirm -- 方案B --> RewardPopup
    RewardPopup --> ReturnCat

    PostRouter -- 方案A: 兑换按钮已消失 --> ExchDisappeared[GoldShellCouponExchangeDisappeared: CheckExchangeDisappearedReco]
    PostConfirm -- 方案A --> ExchDisappeared
    ExchDisappeared --> ReturnCat

    PostRouter -- 无对号且按钮未消失且无结算弹窗 --> ExchFailed[GoldShellCouponExchangeVerifyFailed: StopTask 失败熔断]
    PostConfirm -- 确认后仍无结果 --> ExchFailed

    CheckExchange -- 未命中 --> RetryExchange[GoldShellCouponExchangeRetry: 短暂延迟后再次识别兑换]
    RetryExchange -- 命中 --> PostRouter
    RetryExchange -- 仍未命中 --> NoExchange[GoldShellCouponNoExchange: 判定为无可兑换/已兑换]
    NoExchange --> ReturnCat

    %% 状态驱动两级返回
    ReturnCat --> VerifyCatAfterReturn[GoldShellCouponVerifyCategoryAfterReturn: 确认命中开贝壳_误触识别.png]
    VerifyCatAfterReturn --> ReturnTank[GoldShellCouponReturnTank: 点击分类页左上角返回]
    ReturnTank --> VerifyTank[GoldShellCouponVerifyTank: 命中主界面特征.png -> GoldShellCouponDoneAction]
    
    %% 双出口
    VerifyTank --> DualExit1[DailyRoutineReturnIfActive: active=True -> DailyRoutineDispatcher]
    VerifyTank --> DualExit2[DailyRoutineStandaloneDone: active=False -> 正常退出]
```

---

## 四、核心识别参数与动作规范 (1280×720)

| 节点名称 | 识别方式 | 模板 / Expected | ROI `[x, y, w, h]` | 动作 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GoldShellCouponEntry` | `TemplateMatch` (0.8) | `开贝壳_入口.png` | `[289, 492, 168, 139]` | `Click` | 主鱼缸贝壳入口 |
| `GoldShellCouponVerifyCategoryPage` | `TemplateMatch` (0.8) | `开贝壳_误触识别.png` | `[498, 80, 280, 191]` | `DoNothing` | 贝壳分类页门禁（粉色小章鱼特征） |
| `GoldShellCouponEnterGold` | `OCR` | `^进入$` | `[904, 579, 108, 40]` | `Click` | 分类页右侧金贝壳“进入”按钮 |
| `GoldShellCouponGoldPageIdentity` | `TemplateMatch` (0.8) | `金贝壳_识别.png` | `[515, 360, 232, 195]` | `DoNothing` | 金贝壳主页正向识别模板 |
| `GoldShellCouponVerifyGoldPage` | `Custom` | `CheckGoldShellPageReco` | 必须命中 `金贝壳_识别.png` | `DoNothing` | 金贝壳主页专属门禁（排斥分类页/海星页） |
| `GoldShellCouponGreatButton` | `OCR` | `^太好了$` | `[568, 512, 153, 51]` | `Click` | 点完对号后的结算按钮，点击命中文字后再两次返回 |
| `GoldShellCouponCheckExchange` | `OCR` | `^[兑兌][换換]$` | `[1136, 41, 91, 35]` | `Click` | 右上角兑换按钮（兼容繁简体） |
| `GoldShellCouponExchangeRetry` | `OCR` | `^[兑兌][换換]$` | `[1136, 41, 91, 35]` | `Click` | 兑换按钮重试节点 |
| `GoldShellCouponPostExchangeRouter` | `DirectHit` | - | - | `DoNothing` | 兑换后状态验证路由器；优先识别确认对号 |
| `GoldShellCouponConfirmPopup` | `TemplateMatch` (0.8) | `绿色勾选按钮.png` | `[751, 404, 153, 150]` | `Click` | 消耗确认弹窗对号。此弹窗出现时右上角兑换按钮仍在是正常的 |
| `GoldShellCouponPostConfirmRouter` | `DirectHit` | - | - | `DoNothing` | 点完对号后再核实结算弹窗或兑换按钮消失 |
| `GoldShellCouponRewardPopup` | `OCR` | `^(确定\|確定\|恭喜\|获得\|獲得\|奖励\|獎勵)$` | 全屏 | `Click` | 方案 B: 结算获得弹窗关闭 |
| `GoldShellCouponExchangeDisappeared` | `Custom` | `CheckExchangeDisappearedReco` | `[1136, 41, 91, 35]` | `DoNothing` | 方案 A: 兑换按钮消失确认 |
| `GoldShellCouponExchangeVerifyFailed` | `DirectHit` | - | - | `StopTask` | 状态未变熔断，严禁假完成 |
| `GoldShellCouponReturnCategory` | `OCR` | `返回` | `[0, 0, 189, 146]` | `Click` | 第 1 次返回：从金贝壳页返回分类页 |
| `GoldShellCouponVerifyCategoryAfterReturn` | `TemplateMatch` (0.8) | `开贝壳_误触识别.png` | `[498, 80, 280, 191]` | `DoNothing` | 中间状态门禁：确认退回分类页后方可下发下一点击 |
| `GoldShellCouponReturnTank` | `OCR` | `返回` | `[0, 0, 189, 146]` | `Click` | 第 2 次返回：从分类页返回主鱼缸 |
| `GoldShellCouponVerifyTank` | `TemplateMatch` (0.7) | `主界面特征.png` | `[0, 200, 150, 400]` | `Custom` (`GoldShellCouponDoneAction`) | 确认真正回到鱼缸后标记完成并推进队列 (带幂等防护) |

---

## 五、关键业务设计与防御策略

### 1. 金贝壳主页专属门禁 (`CheckGoldShellPageReco`)
严禁单独使用通用返回按钮作为金贝壳门禁。`CheckGoldShellPageReco` 采用双向验证：
- **严格正向验证**：必须命中 `金贝壳_识别.png`（ROI `[515, 360, 232, 195]`）；
- **严格负向排斥**：检测到贝壳分类页小章鱼、进入按钮或主鱼缸特征时返回 `None`；
- **海星宠物页**：只有返回按钮、没有金贝壳模板时不得过门。命中 `[萌乖亮]海星` 后点击返回，再从 Router 重试。

### 2. 兑换后结果验证 (`GoldShellCouponPostExchangeRouter`)
严禁点击“兑换”后仅靠 `post_delay` 就假定成功并返回。点击后流入状态验证路由器：
- **优先：消耗确认对号** (`GoldShellCouponConfirmPopup`)：实机确认弹窗文案为“兑换金贝壳券需要消耗25个贝壳券，是否继续呢？”，必须先点击绿色对号。此弹窗出现时右上角“兑换”按钮依然存在，这是正常的，不得据此判失败；
- **结算：太好了** (`GoldShellCouponGreatButton`)：点完对号后，在 `[568, 512, 153, 51]` OCR 点击“太好了”，再执行两次返回；
- **方案 A (按钮消失)**：点完对号后再通过 `CheckExchangeDisappearedReco` 核实 `[1136, 41, 91, 35]` 兑换文字已消失；
- **方案 B (结算弹窗)**：通过 `GoldShellCouponRewardPopup` 捕获并关闭获得/结算弹窗；
- **异常熔断 (`GoldShellCouponExchangeVerifyFailed`)**：既没有确认对号、也没有结算弹窗，且兑换按钮仍在，才触发 `StopTask` 熔断，绝不假完成。

### 3. 未识别到“兑换”时的语义收紧
- 只有在金贝壳主页专属门禁成立 + 多次复核均无兑换按钮时，才流转到 `GoldShellCouponNoExchange`，正常结束并安全返回鱼缸。

### 4. 两级状态驱动返回（杜绝盲点连续穿透）
- 第 1 次点击返回后，必须由 `GoldShellCouponVerifyCategoryAfterReturn` 重新命中 `开贝壳_误触识别.png` 确认回到分类页；
- 确认分类页后，才执行第 2 次返回点击；
- 最后必须由 `GoldShellCouponVerifyTank` 命中 `主界面特征.png`，杜绝半途退出导致后续任务失步。

### 5. DoneAction 幂等防护与双出口路由
- **幂等防护**：`GoldShellCouponDoneAction` 检查 `step == "GOLD_SHELL_COUPON"` 且 `status != "DONE"`，重复触发或断点重试时忽略，防止 `queue.pop(0)` 导致调度队列异常弹出；
- **日常收尾中 (`active=True`)**：更新状态并安全推进下一任务，流转回 `DailyRoutineDispatcher`；
- **独立运行时 (`active=False`)**：不触碰调度队列，通过 `DailyRoutineStandaloneDone` 正常退出。
