# 摇一摇小游戏 (ShakeGameTask)

## 功能概述
摇一摇小游戏是游乐园内的体感互动小游戏。开心水族箱原生通过 Android 传感器（Cocos2dxAccelerometer，50Hz 采样率）监听设备摇晃。本助手通过 MuMu 模拟器提供的无感后台管理 RPC（`MuMuManager.exe control -v <vm_index> tool func -n shake`）直接向模拟器底层注入摇动事件，无需抢占鼠标/键盘前台焦点，也不干扰用户操作。

任务实现**默认每日最多 3 局循环**并已集成至**日常收尾任务 (DailyRoutineTask)**。若中途检测到今日次数用尽或体力耗尽，将与金海豚一致标记 `NO_STAMINA`，安全关闭弹窗并推进后续日常任务，不记为错误。

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
