# 钓鱼达人功能设计与状态机规范 (FishingTask)

## 1. 业务目标与完整产品定位

- **功能定位**：自动前往指定钓场，智能检查并选择黄色奶酪（普通饵食），完成自动甩杆、高速咬钩 QTE 识别、精准收杆与结算奖励领取；在鱼饵耗尽或达到硬安全上限后自动优雅退出。
- **阶段演化**：Phase 1 导航已作为正式任务的前半流程，整体任务直接以「钓鱼达人」对外交付。
- **红线约束与零鱼饵安全纪律**：
  - 未经用户授权严禁真实甩杆消耗鱼饵；
  - 任务内置单次运行 `max_casts = 5` 双重硬保护（Action 拦截 + Reco 拦截），防止 UI/OCR 异常导致鱼饵超额消耗；
  - 严禁任何形式的自动购买/代币补充行为，无鱼饵时安全退出（`FishingDone`）。

---

## 2. 步骤可恢复启动契约 (Step-resumable Start Contract)

任务基于「最深已知阶段优先（Deepest-First）」原则，支持从以下 8 个已知阶段自适应恢复，无需强行倒退回第一步：

```text
FishingTask (入口，重置 cast_count=0)
    ↓
FishingStartRouter (最深已知阶段优先路由，按真实截屏自适应恢复)
    ├─ 1. [最深/模态] 误入鱼饵购买弹窗 ──> FishingStartAtPurchasePopup (模板匹配右上角红色×) ─> 点击×关闭 ──> FishingBaitRouter
    ├─ 2. 处于结算弹窗 ───────────────> FishingStartAtCatchResult (OCR "恭喜您获得") ─────────> 自动点击「领取」 ─> FishingLoopRouter
    ├─ 3. [特殊] 已甩杆等待咬钩 ───────> FishingStartAtWaitingForBite (OCR "收杆") ──────────> 进入 WatchOnly 高速监听 ─> FishingPostRoundRouter
    ├─ 4. 已选鱼饵可直接甩杆 ─────────> FishingStartAtReadyWithBait (OCR "更换鱼饵") ─────────> FishingRound (自动钓鱼)
    ├─ 5. 未选鱼饵场景 ───────────────> FishingStartAtNeedBait (OCR "选择鱼饵") ──────────────> 打开选饵抽屉 ─> 选黄色奶酪 ─> FishingRound
    ├─ 6. 钓鱼地点选择大地图 ─────────> FishingStartAtLocationMap (OCR "钓鱼达人") ──────────> 选配置地点 ─> FishingBaitRouter
    ├─ 7. 2×6 游乐园活动弹窗 ──────────> FishingStartAtActivityGrid (模板匹配鱼竿) ───────────> 点击进入大地图
    └─ 8. [最浅] 自身水族箱主界面 ───────> FishingStartAtOwnTank (模板匹配主界面) ─────────────> 点击摩天轮进入游乐园
```

> [!NOTE]
> **关于 WatchOnly 中途恢复的时效性说明**：  
> 当用户在“已甩杆等待中（收杆）”阶段中途重启任务时，系统具备 WatchOnly 恢复能力，但因重启与 Pipeline 阶段识别存在几百毫秒的调度耗时，属于**有条件恢复能力**（若感叹号恰好在重启瞬间出现，仍存在理论错失窗口）。而在正常自动钓鱼主流程中，高速监听是在甩杆前毫秒级预备就绪的，完全不受调度时延影响。

---

## 3. 完整自动钓鱼状态机流向

```text
FishingBaitRouter
    ├─ PurchasePopup (模板匹配红色×) ─────> FishingBaitPurchasePopup (点击×关闭弹窗并返回)
    ├─ AlreadySelected (OCR "更换鱼饵") ──> FishingRound
    ├─ NeedSelect (OCR "选择鱼饵") ────────> OpenBaitPicker ──> SelectCheese (点击黄色奶酪) ──> VerifyReady ──> FishingRound
    └─ NoBait ─────────────────────────────> FishingDone (安全退出)

FishingRound
    ↓ (执行单次甩杆，触控保持 60ms 确保必触发，cast_count += 1)
FishingCastAndBiteQTEAction (高速抓帧 ~46~58 FPS + ColorGeometry 检测 1ms)
    ↓ (首次检出感叹号即刻下发触控收杆，时延仅 41ms)
FishingPostRoundRouter
    ├─ CatchSuccess (OCR "恭喜您获得") ──> 点击「领取」 (642, 584) ──> post_delay ──> FishingLoopRouter
    ├─ ReadyAgain (失败/未中自然恢复，OCR "甩杆") ──> FishingLoopRouter
    └─ Unknown (有界等待 bounded wait，超时后安全退出保存现场)

FishingLoopRouter
    ├─ 检查上限 (cast_count >= 5) ────────> FishingDone
    ├─ 仍有鱼饵 (OCR "更换鱼饵") ──────────> FishingRound (开启下一杆)
    ├─ 需选鱼饵 (OCR "选择鱼饵") ──────────> FishingBaitRouter
    └─ 其它/无饵 ──────────────────────────> FishingDone
```

---

## 4. 鱼饵安全规则与防误触禁区 (Bait & Purchase Safety)

1. **选择规则**：
   - 自动化仅允许选择玩家已有的“普通饵食”；
   - 普通饵食文字可用于辅助识别栏位，**实际选择动作采用模板匹配 (`普通饵食_黄色奶酪.png`) 精准点击最左侧黄色奶酪图标本体**；
   - 蓝色 / 绿色 “+” 属于购买入口：**绝对禁止点击**！
2. **几何禁区保护**：
   - 黄色奶酪中心位于 $x=101.5$，购买 “+” 位于 $x=394.5$，**物理间距高达 293 像素**；
   - 奶酪识别 ROI 严格限制在 $[50, 380, 120, 100]$，距离购买入口右边界保持 209 像素以上的绝对缓冲余量，模板在加号区域置信度仅 0.2524，杜绝任何误触可能。
3. **误入购买弹窗恢复 (Purchase Safety Guard)**：
   - 购买弹窗属于遮挡模态页面，若被用户或其他偶发操作打开，状态机最高优先级触发 `FishingBaitPurchasePopup`（模板匹配右上角 `鱼饵购买弹窗_关闭.png`）；
   - **唯一合法动作为点击右上角红圈白 × 关闭弹窗**，严禁点击任何货币、商品、确认按键；关闭后安全返回选饵路由。
4. **硬安全上限 (`max_casts = 5`)**：
   - Action 层：`FishingCastAndBiteQTEAction` 在发送点击前检查 `cast_count >= 5`，超限立即拦截并返回 `False`；
   - Reco 层：`CheckFishingCastLimitReco` 在 Pipeline 循环处判定是否达标，达标直接跳转至 `FishingDone`。

---

## 5. Phase 2B 实机真实咬钩时序测量数据 (Golden Telemetry)

在真实 MuMuPlayerExtras 环境下使用 1 枚真实鱼饵进行的实机抓帧与闭环验证：

| 指标项 | 实测测量值 | 说明 |
| :--- | :--- | :--- |
| **实测抓帧帧率** | **46.12 FPS** | 平均帧间隔 21.6ms，原生 IPC 渲染器共享内存取帧 |
| **甩杆到咬钩等待期** | **9.32 秒** | 抛竿蓄力动画约 1s，随后浮漂在水面浮动约 8s |
| **感叹号初露微光时刻** | **$T+9322\text{ ms}$** (Frame #431) | 0.5x 缩放半透明渐入 |
| **Detector 首次强命中** | **$T+9426\text{ ms}$** (Frame #436) | 双连通域完美垂直对齐，检出延迟仅 **104.32 ms** |
| **收杆触控下发完成** | **$T+9467\text{ ms}$** (Frame #437) | 点击下发耗时 **41.28 ms**，距感叹号初现仅 **145.60 ms** |
| **实战战报结果** | **成功捕获「巨蛇座 x1」** | 成功弹出结算界面，秒级命中咬钩有效窗口 |
| **自然咬钩最大逃跑窗口**| **【仍未知】** | 触控在 145.6ms 时已生效，收杆动画打断了咬钩过程，未有脱钩自然时序 |
| **成型期识别率 (Recall)**| **83.3% (5/6 帧)** | 严格过滤水纹与手柄干扰，零误报 |
