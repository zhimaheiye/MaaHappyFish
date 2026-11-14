# 摇一摇小游戏 (ShakeGameTask)

## 2026-11-08 入场确认误判耗尽（已随 v0.8.1 发布）

本机 `log-20261108.log` 显示第一局正常完成后，10:37:50 导航将下一次确认误判为「机会用完」，点击 `(824,480)` 后又点击 `(891,489)` 两次并报告关窗失败。同期原始错误帧 `client_avalonia/debug/on_error/2026.11.08-10.37.54.420_ShakeGameNavigation.png` 实际是第二局进行中，左上倒计时 11.6 秒、右上分数 10；用户稍后截图是该局自然结束。旧代码用固定小块中未发现红叉推断次数耗尽，转场或按钮尚未呈现时会误判；局内绿色背景又能被宽泛绿色按钮定位器当成对勾，导致跨层补点。缺少误判那一帧，不能进一步确定红叉当时的渲染状态。11:04 同一耗尽分支正常通过，不能把所有耗尽分支都判为故障。

现改为在当前帧中通过 `ShakeGameConfirmIdentity` 的「想玩…小游戏」或 `ShakeGameExhaustedIdentity` 的「机会…用完／明天再来」正文正向区分，再定位确认按钮；正文最多等约 3 秒，未知态失败且不点击。不再加载可选 RapidOCR，也不以按钮缺失推断耗尽。正常入场只点一次，随后最多约 4 秒等待局内或结算门禁；耗尽补点前须重新确认正文和按钮，正文消失后停止补点并确认主鱼缸才报告 `NO_STAMINA`。

新增局内门禁要求同帧命中右上 `[1050,0,230,90]` 的「分数」和左上 `[0,0,220,90]` 的小数秒数。它既用于确认入场后状态，也支持从已取证局内接手；不沿用历史进度，也不重置或额外增加完成局数。其它小游戏与未知页仍安全停止。

使用本机已安装的 MaaDebugger 1.20.1 及项目匹配的 MaaFramework 5.12.3，在保存的错误截图上确认两项 OCR 及组合门禁命中；分数置信度 0.945343，倒计时 0.940993。鱼缸选择器作为局内负例。仅做真实截图识别调试，未运行游戏任务；当前缺少本次入场和耗尽弹窗原图，相关正文分支未做实机验收。既有摇一摇与近期事故 18 项通过，316 条正则、995 节点资源加载、Agent 引用及编译通过。11月8日修复时未新增测试或辅助脚本、未改用户配置、未联网同步或推送；11月14日已随 v0.8.1 发布。

## 2026-11-03 跨小游戏误导航修复（已随 v0.8.1 发布／仅代码级验证）

11 月 3 日 11:24 的错误帧是其它小游戏的「游戏结束」页面。旧导航只要未命中游乐园面板就继续搜索游乐园入口，等价于把未知页当成主鱼缸，可能在金海豚局内／结果转场后跨层误点。现只有 `主界面特征.png` 达到门禁后才允许点击游乐园入口；结算页和已打开面板仍按 deepest-first 接手，其它小游戏、浪漫满屋及未知活动页均真实失败且零入口点击。次数／体力耗尽弹窗点击后也必须以新帧确认已关闭，关闭失败不再返回 `NO_STAMINA`。代码级验证完成，本次未运行 MFA、MuMu RPC 或游戏任务。

## 功能概述
摇一摇小游戏是游乐园内的体感互动小游戏。开心水族箱原生通过 Android 传感器（Cocos2dxAccelerometer，50Hz 采样率）监听设备摇晃。本助手通过 MuMu 模拟器提供的无感后台管理 RPC（`MuMuManager.exe control -v <vm_index> tool func -n shake`）直接向模拟器底层注入摇动事件，无需抢占鼠标/键盘前台焦点，也不干扰用户操作。

任务实现**默认每日最多 3 局循环**并已集成至**日常收尾任务 (DailyRoutineTask)**。若中途检测到今日次数用尽或体力耗尽，将与金海豚一致标记 `NO_STAMINA`，安全关闭弹窗并推进后续日常任务，不记为错误。

## Start Contract

- 支持从已确认主鱼缸、游乐园面板、进入确认弹窗、同帧具有分数与小数秒倒计时的已取证局内页，以及结算页启动；其它小游戏或未知活动页不导航。
- 启动帧命中 `金海豚_结束取消.png` 时设置 `SETTLEMENT`，直接执行 `ShakeGameExitAction`；退出动作只在模板命中后点击，并把该局计数一次。
- 局内接手须同帧命中左上倒计时与右上分数；当前只验证 2026-11-08 的已取证页面，不用“入口没找到”反推局内，也不默认 VM index 0。
- MuMuManager 路径、VM index、RPC 频率、失败熔断与三局上限未改变。本次仅做离线代码验证，未操作模拟器。

---

## 核心状态机模型

```text
ShakeGameTask (ShakeGameInitAction: IDLE, completed=0, max=3)
       │
       ▼
ShakeGameNavigation (ShakeGameNavigationAction)
       ├─ 无体力/次数用尽 ──> [NO_STAMINA] ──> ShakeGameDone
       └─ 成功进入小游戏 ──> [READY_TO_PLAY]
                                   │
                                   ▼
                            ShakeGamePlay (CheckShakeGameCanPlayReco 门禁)
                                   │
                                   ▼ (ShakeGamePlayAction: PLAYING)
                            MuMuManager shake RPC 循环 (0.8s 间隔)
                                   │
                                   ├─ 连续 3 次 RPC 失败 ──> [FAILED] (安全熔断，返回 False)
                                   ├─ 40s 超时未见结算 ──> [FAILED] (保留现场，严禁盲点假装成功)
                                   ├─ 任务取消 ──────────> [FAILED] (返回 False)
                                   └─ 检出结算弹窗 ──────> [SETTLEMENT]
                                                               │
                                                               ▼
                                                        ShakeGameExit (ShakeGameExitAction)
                                                               │ (识别并点击结算取消按钮)
                                                               ├─ completed < max_rounds ──> [NEXT_ROUND]
                                                               │                                  │
                                                               │                                  ▼
                                                               │                           ShakeGameRepeat
                                                               │                           (重新导航进入下一局)
                                                               │                                  │
                                                               │                                  ▼
                                                               │                         ShakeGameNavigation
                                                               └─ completed >= max_rounds ─> [DONE]
                                                                                                  │
                                                                                                  ▼
                                                                                           ShakeGameDone (ShakeGameDoneAction: 推进日常)
                                                                                            ShakeGameVerifyTank (主界面特征.png 确认)
                                                                                                   │
                                                                                ┌──────────────────┴──────────────────┐
                                                                                ▼                                     ▼
                                                                    DailyRoutineReturnIfActive            DailyRoutineStandaloneDone
                                                                    (CheckDailyRoutineActiveReco)         (DirectHit -> DoNothing 叶子)
                                                                                │                                     │
                                                                                ▼ (日常激活)                           ▼ (独立运行)
                                                                      DailyRoutineDispatcher               任务正常结束退出
```

### 运行时状态字典 (`runtime_state.shake_game_state`)
- `IDLE`: 任务初始化或就绪；
- `READY_TO_PLAY`: 导航确认成功，已进入小游戏准备开始摇晃；
- `PLAYING`: 正在循环调用 MuMuManager 发送 shake RPC；
- `SETTLEMENT`: 视觉检出结算弹窗，摇晃阶段结束；
- `NEXT_ROUND`: 单局退出完成，且尚未达到 3 局上限，准备进入下一局；
- `DONE`: 3 局全部完成，已收起抽屉并退出到主鱼缸；
- `NO_STAMINA`: 识别到今日次数已用完，正常结束并推进日常收尾；
- `FAILED`: 模拟器路径/VM index 缺失、连续 RPC 失败、超时未结算或异常终止。

---

## 关键技术实现与安全防护

### 1. 严格获取 VM Index 与 MuMuManager（禁止猜测默认值）
- 从 `context.tasker.controller.info` 读取运行配置；
- 支持优先从 `extras.mumu.path` 定位 `nx_main/MuMuManager.exe`，或从 `adb_path` 同级目录推导；
- **VM index 门禁**：必须明确从 `extras.mumu.index` 取得；若缺失或为 None，严格返回 `(None, None)` 并终止任务，**绝不回退到默认 0**，防止多开实例时摇错模拟器。

### 2. MuMuManager RPC 双重安全判定
- 执行命令：`MuMuManager.exe control -v <vm_index> tool func -n shake`；
- 执行参数：`shell=False`、`capture_output=True`、`timeout=2.0`；
- 成功门禁：必须同时满足 `proc.returncode == 0` 且 stdout 输出的 JSON 中 `errcode == 0`；
- 熔断机制：若连续 3 次 RPC 失败，立即记录 ERROR 日志并终止任务，防止死循环无效调用。

### 3. 防盲点设计与超时保护
- 摇晃主循环中，每 0.8s 注入一次 shake 事件，并在每次间隔中采样截屏检测结算弹窗（复用 `金海豚_结束取消.png` 模板匹配，阈值 0.70）；
- 若达到最大时长 `SHAKE_GAME_MAX_DURATION_SECONDS = 40.0s` 仍未检出结算弹窗，记录显式 ERROR 并直接返回 `False`，**坚决杜绝在未识别到结算时盲点固定坐标假装成功**；
- 结算退出动作 `ShakeGameExitAction` 中，必须通过模板匹配精确计算结算取消按钮中心坐标并下发点击；若未识别到取消按钮则安全终止以保留现场。

### 4. 每日 3 局循环与日常收尾集成
- 默认执行最多 3 局循环（`max_rounds = 3`）；
- 已集成至 `DailyRoutineTask`，执行顺序排在 `GOLDEN_DOLPHIN` 之后、`FISHING` 之前；
- 在 `DailyRoutineTask` 流程中结束时，通过 `ShakeGameDoneAction` 自动调用 `advance_daily_routine_step("ShakeGame", st)`，将状态沉淀并调度下一子任务；
- 若作为独立任务运行，`daily_routine_state["active"]` 为 False，通过双出口路由节点 `DailyRoutineStandaloneDone` 正常成功结束，杜绝跌入未激活的 Dispatcher 产生 20 秒超时失败；若在日常收尾中运行，则由 `DailyRoutineReturnIfActive` 路由回 `DailyRoutineDispatcher` 推进后续子任务；
- `interface.json` 的 `日常收尾任务` 选项已默认勾选 `摇一摇`。

---

## 视觉与资源依赖速查
- `assets/resource/image/游乐园入口.png`：主鱼缸右侧游乐园入口识别；
- `assets/resource/image/摇一摇_入口.png`：游乐园网格内摇一摇小游戏图标识别；
- `assets/resource/image/金海豚_确定按钮.png`：进入小游戏确认弹窗（绿色对号按钮）；
- `assets/resource/image/金海豚_结束取消.png`：小游戏结束结算弹窗取消按钮；
- `assets/resource/image/主界面特征.png`：返回主鱼缸最终视觉验证。

## 验证状态

- 2026-09-24 结算页恢复路由、单局只计一次、三局循环、VM index 不得默认 0、RPC 熔断与独立/日常双出口通过离线专项；Pipeline 正则/资源加载与 Agent 引用门禁通过。
- 2026-11-08 已补局内真实帧双 OCR 门禁并通过 MaaDebugger 截图识别调试；未操作模拟器，完整恢复和弹窗正文分流仍待自然运行验收。
