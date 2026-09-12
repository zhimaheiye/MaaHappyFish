# 开贝壳活动自动化 (docs/features/open-shell.md)

## 功能定位
开心水族箱限时/常驻活动“大章鱼开贝壳”自动化小助手。支持用户设定连续执行次数 $N$，普通奖励始终选择继续开贝壳，遇章鱼固定保留一个随机奖品，自动完成多轮闭环领奖。

## ⚠️ 任务启动前置条件（重要）
- **必须在大章鱼开贝壳活动主界面开始任务**（画面中需能够匹配 `开贝壳_识别.png` 页面特征，并能够 OCR 识别绿色「立即开始」按钮）。
- 自动化不会自动跨层级寻找活动入口，请人工打开活动页面后再在客户端中勾选启动。

---

## 状态机流转设计

```text
OpenShellTask (入口)
    ↓
OpenShellStartPage (模板确认大章鱼活动主页)
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
    └─ 轮次已达 (>= N) ─> OpenShellDone (DoNothing 任务正常结束)
```

---

## 核心设计决策与容错保障

### 0. 页面门禁与返回动作

- `开贝壳_识别.png` 是用户提供的大章鱼页面本体模板，识别 ROI 为 `[508,70,263,201]`。独立 `OpenShellTask` 必须先命中该门禁，才进入「立即开始」OCR 流程。
- `贝壳页面_返回.png` 只截取左上角返回按钮，ROI 为 `[0,0,250,150]`，只能在页面本体门禁通过后用于识别点击，不能单独证明当前是大章鱼页面。2026-09-12 报告已确认鱼缸管理页存在同款按钮并可达到 0.999998 的错误匹配；巡检与收鱼流程现均遵守这套两阶段门禁。
- 其他任务处理误入大章鱼页面时应复用“页面本体门禁 -> 返回按钮点击”的两段契约，不得改用 `活动页面_退出.png` 通用活动页模板。多鱼缸巡检通过 `[JumpBack]PatrolShellPagePopup` 接入该流程。

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
