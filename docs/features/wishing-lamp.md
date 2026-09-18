# 许愿神灯自动化 (docs/features/wishing-lamp.md)

**最后更新**: 2026-09-18

## 功能定位

开心水族箱"许愿神灯"活动自动化（`WishingLampTask`，独立任务）。参考开贝壳模块的分层门禁结构：从主鱼缸进入神灯选择主页，OCR 点击灯名文字进入任意神灯，循环点击「许愿绸」累计鱼碎片，完成后两级退出回主鱼缸。

## Start Contract（三态步骤可恢复）

Deepest-First 启动路由，任意状态均可启动：

1. **已在神灯内部**（最深）：ROI `[1022,458,68,38]` 识别 `许愿绸.png` 确认，直接进入许愿循环；
2. **已在神灯选择主页**：ROI `[0,0,201,129]` 识别 `许愿神灯_识别.png`（主页左上装饰）确认，直接定位灯名；
3. **在主鱼缸**：ROI `[145,171,35,22]` 识别 `许愿神灯_入口.png` 点击 → `许愿神灯_识别.png` 确认到达选择主页；
4. 未知页面：`WishingLampAbort`（StopTask）安全停止，不盲点。

## 状态机

```text
WishingLampStartRouter
    ├─ 已在神灯内部 ──────────────> WishingLampLoopRouter
    ├─ 已在选择主页 ──> WishingLampOpenLamp ──> VerifyInLamp ──> LoopRouter
    └─ 主鱼缸 ──> MainTankEntry ──> VerifySelectPage ──> OpenLamp ──> ...
                          │
WishingLampLoopRouter ────┘
    ├─ WishingLampPauseCheck（仅"遇暂停条件即停止"模式）── 识别到暂停条件 → StopTask 等用户处理
    ├─ WishingLampShouldContinue（CheckWishingLampContinueReco 计数）
    │       └─ 未达次数 ──> WishingLampClickSilk（点击许愿绸，post_delay 5000）──> LoopRouter
    └─ 达到次数 ──> WishingLampDone
                          │
WishingLampExitInner ── 灯内右上角 X ──> VerifySelectPageAfterExit（许愿神灯_识别 确认）
    ↓
WishingLampExitSelect ── 选择主页 X ──> WishingLampVerifyMainTank（主界面特征 确认）
```

## 关键设计

- **目标神灯参数**（option `许愿神灯选择`，默认幸运神灯）：幸运/开心/欢乐/魔法/青春/奇迹/活力/欢欣/玲珑/元气/童趣共 11 档，每档 pipeline_override 覆盖 `WishingLampOpenLamp.expected` 为对应灯名；
- **灯名点击文字本身 + 滑动查找**：选择主页灯名为横滑列表，识别 ROI `[68,459,1213,83]`（只框定高度，横向随意拖动），OCR 点击命中框中心即文字本身。指定灯不在当前屏时，`WishingLampSwipeLampList` 在确认仍处选择主页（许愿神灯_识别 门禁）后向左滑动（`[1000,360]→[280,360]`，post_delay 1000）并重新 OCR，`max_hit: 12` 为宽松上限——耗尽仍未找到指定灯则安全停止，不无限循环。
- **许愿节奏**：`许愿绸.png` 命中点击，`post_delay: 5000` 等待 5 秒再进行下一次。
- **计数**：`CheckWishingLampContinueReco` 按 task_id 隔离，与 `CheckOpenShellLoopReco` 同构；LoopRouter 首次到达在首次点击之前，因此评估序号 `<= target` 才命中，严格点击 N 次。
- **两种模式**（interface option `许愿神灯模式`，pipeline_override 控制 LoopRouter.next）：
  - `连续许愿（默认）`：LoopRouter 不含 PauseCheck，即使页面出现暂停条件图标也不检查，点满次数后正常退出；
  - `遇暂停条件即停止`：每轮点击后检查 `[583,135,130,127]` 的 `许愿神灯_暂停条件.png`（时钟图标），命中即 StopTask 结束任务等待用户手动处理，不再退出、不再点击。
- **许愿次数**（option `许愿神灯许愿次数`）：5/10（默认）/20/50。
- **两级退出**：复用同款 `许愿神灯_退出.png`（右上角黄 X，两页同位置），每次点击后分别用 `许愿神灯_识别.png`（选择主页）与 `主界面特征.png`（主鱼缸）确认，杜绝盲点连点。

## 用户提供的模板资产（不得改动）

| 模板 | ROI | 用途 |
| --- | --- | --- |
| `许愿神灯_入口.png` | `[145,171,35,22]` | 主鱼缸神灯入口（金灯图标） |
| `许愿神灯_识别.png` | `[0,0,201,129]` | 选择主页门禁（左上装饰） |
| `许愿绸.png` | `[1022,458,68,38]` | 神灯内部许愿绸按钮（兼作灯内门禁） |
| `许愿神灯_退出.png` | `[1226,22,38,37]` | 右上角黄 X（灯内/选择主页两级退出） |
| `许愿神灯_暂停条件.png` | `[583,135,130,127]` | 暂停模式条件图标（时钟） |

## 验证状态

- `dev/test_wishing_lamp.py` 11 项通过：模板/ROI 契约、三态恢复、两级退出、计数严格 N 次（无 off-by-one）、task_id 隔离、三种启动状态全流程、暂停模式 StopTask、连续模式不受图标影响、interface 契约。
- 2026-09-19 新增目标神灯参数与滑动查找（11 档 override + SwipeLampList max_hit 12），`dev/test_wishing_lamp.py` 13 项（含滑动命中与超限安全停止）全部通过；代码级验证完成。
- 代码级验证完成；识别命中率与实际交互（尤其横滑列表 OCR、滑动步长是否恰好跨一屏、暂停条件出现时机）待用户在 MFA 实机验证。
