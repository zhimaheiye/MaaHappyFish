# 海獭摸宝自动化 (docs/features/sea-otter-gem.md)

**最后更新**: 2026-09-13

## 功能定位

开心水族箱海獭寻宝特定宝石自动化助手（`SeaOtterGemTask`）。针对用户在海獭寻宝中选定特定宝石并进入寻宝好友列表/鱼缸的场景，自动化在相邻好友之间往复切换、高效摸取目标宝石，并在好友体力耗尽后自动向后滑动窗口。到达末位好友后，右侧系统推荐玩家只作为返回末位好友的跳板，不执行摸宝。

---

## 核心业务模型：LEFT / RIGHT 双端窗口语义

### 第一原则：`Current UI State > History`

**绝对不保存**：
- 好友历史体力记录
- 宝石采集数量
- 每个好友摸了几次
- 好友进度（第几号）
- 14/22 之类绝对顺序

状态机仅由**当前帧截图**判定，不依赖任何历史变量。

---

### 窗口语义与 side 变量

运行时始终维护一个 `current_side`，取值为 `"left"` 或 `"right"`。

| side 值 | 含义 |
| :--- | :--- |
| `"left"` | 当前正在处理的好友是窗口的左侧主力好友 |
| `"right"` | 已进入右侧好友鱼缸（点击了 Next 导航到右邻好友）|

---

### 核心分支规则（实际代码逻辑）

#### 当 UI 识别到「刷新体力」（Exhausted）时：

```
side == "left"  → ADVANCE_WINDOW_NEXT
    → post_click(1205, 68)  [Next 按钮]
    → side 保持 "left"（新进入的好友是新的 LEFT）
    → consecutive_exhausted += 1

side == "right" → PREV_AS_REFRESH_BRIDGE
    → post_click(1085, 68)  [Prev 按钮]
    → side 切回 "left"（返回原 LEFT 好友）
    → consecutive_exhausted 不增加
```

> **RIGHT exhausted 不代表窗口推进。** RIGHT 耗尽时仅退化为跳板（bridge），下一次仍在 LEFT 好友鱼缸开始，LEFT 好友被再次刷新可摸。
>
> **LEFT exhausted 才代表窗口向右推进。** Next 之后，原 RIGHT 成为新的 LEFT。

#### 当 UI 可摸（Harvestable）时：

```
side == "left"  → HARVEST_THEN_NEXT
    → 点击海獭 (85, 565)
    → post_click(1205, 68)  [Next → 进入 RIGHT 好友]
    → side 切为 "right"

side == "right" → HARVEST_THEN_PREV
    → 点击海獭 (85, 565)
    → post_click(1085, 68)  [Prev → 返回 LEFT 好友]
    → side 切回 "left"
```

#### 好友身份门禁与末位推荐玩家：

- 当前页面命中 `好友判断_已点赞.png` 或 `好友判断_未点赞.png` 任一模板，才认定为真实好友，并进入耗尽/可摸状态识别。
- 两种模板都未命中时，禁止点击海獭。若页面仍有好友导航箭头，则认定为末位好友右侧的系统推荐玩家：
  - `side == "right"`：只点击 Prev 返回最后一个真实好友，继续摸宝；
  - `side == "left"`：说明末位好友已耗尽后通过 Next 进入推荐玩家页，记录 `LAST_FRIEND_EXHAUSTED` 并正常完成，不再报桥接状态错误。
- 若真实好友页面命中 `好友切换_灰色右键.png`（ROI `[1124, 0, 156, 134]`），说明好友列表已满且当前位于末位好友：仍可摸时只摸当前好友、不点击不可用的 Next；识别到“刷新体力”后正常完成。

---

### 正确的体力耗尽识别方式

**只认「刷新体力」三个字的 OCR 命中**。

**历史曾错误引入的 fallback**（已废除，绝不恢复）：

| 错误模式 | 问题 |
| :--- | :--- |
| `expected: "0("` | `(` 是 std::regex 特殊字符，导致整个 Pipeline 加载失败 |
| `expected: "0点"` | 过于宽泛，可能误匹配其他 OCR 结果 |
| 依赖数字体力计数 | 违反 `Current UI State > History` 原则 |

**正确做法**：`expected: "刷新体力"`，匹配稳定，无特殊字符，ROI 覆盖 `[60, 210, 350, 170]`。

---

### 连续耗尽 Skip 与防死循环

当多个相邻好友连续耗尽时：
- 每次 LEFT exhausted → Next，side 保持 left，`consecutive_exhausted += 1`
- `CheckSeaOtterLimitReco` 检查 `consecutive_exhausted >= max_consecutive_exhausted (30)`
- 触发上限时安全退出，输出 `Safety Limit Triggered`
- **任何一次摸宝成功（Harvest）都会重置 `consecutive_exhausted = 0`**

---

### SeaOtterDone 的触发条件

1. **启动时已位于完整推荐好友列表页**：OCR 识别到“全部添加”或“推荐好友”；
2. **末位好友耗尽后进入推荐玩家页**：`completion_reason == LAST_FRIEND_EXHAUSTED`；
3. **末位好友右键变灰且体力耗尽**：好友身份门禁通过后，命中灰色右键模板与“刷新体力”；
4. **Safety Limit 触发**：`total_harvests >= max_harvests (200)` 或 `consecutive_exhausted >= 30`。

**绝对不允许**仅因为遇到普通 exhausted 好友，或以 `side == "right"` 进入单个系统推荐玩家鱼缸，就触发 `SeaOtterDone`。

---

### 步骤可恢复启动契约 (Start Contract)

`SeaOtterGemStartRouter` 支持从以下状态就地恢复：

| 启动状态 | 识别方式 | 恢复行为 |
| :--- | :--- | :--- |
| 任意好友鱼缸 | OCR `剩余\|刷新体力`（状态栏）| 就地把当前鱼缸视为第 1 个 LEFT 好友 |
| 寻宝好友列表首页 | 模板匹配列表特征 | 点击首位好友进入 |

**绝不**从非寻宝场景强行进入。

---

### 实机验证状态

| 测试场景 | 验证方式 | 状态 |
| :--- | :--- | :--- |
| A: L摸 → R摸 → L摸 → R摸（对称双好友） | `dev/test_sea_otter_scenarios.py` Mock | **PASS** |
| B: L摸 → R耗尽(Bridge) → L摸 → R耗尽(Bridge) | Mock | **PASS** |
| C: L1耗尽 → L2(旧R)耗尽 → L3正常 → 采集 | Mock | **PASS** |
| D: 多次耗尽后遇可摸好友，旧exhausted绝不触发Done | Mock | **PASS** |
| E: 最后好友摸宝 → 右侧推荐玩家 → 返回最后好友并继续摸宝 | Mock + Pipeline 静态检查 | **PASS（代码级）** |
| F: 最后好友耗尽 → 进入推荐玩家 → 正常完成 | Mock + 日志复现 | **PASS（代码级）** |
| G: 好友列表已满，灰色右键末位好友继续摸宝并在耗尽后完成 | Mock + Pipeline 静态检查 | **PASS（代码级，MFA 待验证）** |
| 真实长循环（不对称好友体力实机运行）| 用户实机观测 | **PASS（v0.4.2 验证）** |
| 末位好友与右侧推荐玩家反复桥接 | MFA 实机 | **PASS（2026-09-09，终止分支修复前）** |
| 推荐玩家边界正常终止 | MFA 实机 | **PASS（2026-09-13，主力机连续两轮）** |
| 灰色右键边界正常终止 | MFA 实机 | **待验证** |

2026-09-11 重新执行 `dev/test_sea_otter_scenarios.py`，8 个场景全部通过；台式机反馈的“末位好友右侧按钮变灰后卡住”已确认由现有灰色右键专用门禁覆盖。该 Bug 已完成代码级验证并从 `ISSUES.md` 移除，本次未做模拟器测试。

### 2026-09-13 主力机运行与闪退观察

- 18:15 开始的长轮次稳定执行到累计 79 次摸宝后，MFA 日志无 Python 异常、Maa 失败或海獭状态错误而直接中断。Windows 在 18:23:20 记录虚拟内存不足：`MuMuNxDevice.exe`、`start_server.exe`、`ChatGPT.exe` 分别使用约 5.21、4.17、1.85 GiB；随后 MFA 在 18:24:27 和 18:26:49 两次以相同的 `ucrtbase.dll / 0xc0000409` 原生异常退出，18:26:57 又出现 `dwm.exe / dwmcore.dll` 崩溃。当前证据更支持整机资源压力或原生运行时不稳定，不支持把闪退归因于海獭业务状态机，但尚不能断言唯一根因。
- 后续两轮分别运行 3 分钟和 5 分 25 秒并正常完成。末位好友可摸时，日志多次出现 `RIGHT + RECOMMENDED -> PREV_AS_LAST_FRIEND_BRIDGE` 返回末位好友继续摸宝；末位好友出现「刷新体力」后，再由 `LEFT + RECOMMENDED -> DONE_LAST_FRIEND_EXHAUSTED` 正常结束。这与当前边界状态机设计一致。
- 据此，“最后一个好友与非好友交界处只能摸取 5~6 次”的待办按用户决定从 `ISSUES.md` 移除，本轮不修改代码。主力机性能高于此前出现问题的台式机，机器性能差异保留为观察变量；若台式机再次出现，使用当次 MFA 日志与 Windows Application/System 事件重新立项排查。

---

## 已知限制与 Pending 工作

### ⚠️ Known/Pending: NO_TARGET_IN_CURRENT_TANK 短暂提示

**现象描述**：

进入某些好友鱼缸时，游戏会**在页面切换瞬间**自动显示类似：

> "这个鱼缸没有可以摸取……去好友别的鱼缸……"

的短暂提示文字。

**关键事实**（已实机观察确认）：

| 特征 | 描述 |
| :--- | :--- |
| 触发时机 | 切换到该好友家时**自动出现**，不是点击海獭后出现 |
| 持续时间 | 极短（约 1~2 秒），会自动消失 |
| 好友体力状态 | 好友左侧仍可能显示「10 剩余」，并非 Exhausted |
| 业务含义 | 该好友当前鱼缸没有目标宝石（但好友体力正常，可能有其他鱼缸有） |
| 手动玩家行为 | 切换到该好友的另一个鱼缸再摸宝 |

**与 Exhausted 的本质区别**：

- Exhausted = 好友今日体力已耗尽，所有鱼缸都无法摸
- NO_TARGET_IN_CURRENT_TANK = 当前鱼缸无目标宝石，但好友体力正常

**当前脚本处理策略**：

当前版本**暂不实现好友内部换缸**。遇到此提示，视为不影响正常流程继续（提示消失后正常进行摸宝尝试）。

**正式完整实现需要的技术方案**：

由于提示显示时间极短，**不能等待页面稳定后再截图 OCR**。

正确探索方法：
1. 在点击 Next/Prev 切换好友之前，启动连续高速截图（burst capture）
2. 点击导航后立即进行连续截图（ring buffer / 内存留帧）
3. 页面切换完成后离线 OCR 历史帧（peak / first / last / duration 记录）
4. **绝不在高速抓帧热循环里每帧跑重量级 OCR**（性能禁区）

**当前状态**：🔴 **Pending** — 尚未实现正式检测与处理逻辑，是下一阶段优化候选项。

---

## 核心文件速查

| 文件 | 说明 |
| :--- | :--- |
| `agent/runtime_state.py` | `sea_otter_gem_state` 共享状态字典 |
| `agent/my_action.py` | `InitSeaOtterStateAction`, `SeaOtterHarvestAction`, `SeaOtterAdvancePairAction`, `SeaOtterReturnFromRecommendedAction` |
| `agent/my_reco.py` | `CheckSeaOtterLimitReco` |
| `assets/resource/pipeline/features/sea_otter_gem.json` | `SeaOtterGemTask` 状态机 Pipeline |
| `dev/test_sea_otter_scenarios.py` | 8 项业务场景、好友身份门禁与末位终止验证（无需设备） |

---

## 维护注意点

1. **不要恢复任何数字体力计数逻辑**（`0(`、`0点`、`12点`等），这条路已经导致过 Pipeline 加载失败。
2. **Right exhausted ≠ 推进窗口**，只需退回 Left；推进只由 Left exhausted 触发。
3. `consecutive_exhausted` 计数只在 LEFT exhausted → Next 时增加，Harvest 时归零。
4. 修改 Pipeline 后必须运行 `python dev/test_pipeline_regex.py` 检查正则。
5. `好友判断_已点赞.png` 与 `好友判断_未点赞.png` 是真实好友的正向身份依据；未通过身份门禁时禁止摸宝。
6. `好友切换_灰色右键.png` 只在真实好友门禁通过后判断；可摸时留在末位好友，耗尽后才完成。
7. 好友摸宝的 `好友摸宝快捷键_可用.png` / `好友摸宝快捷键_不可用.png` 不适用于海獭摸宝；本任务仍只点击左下角海獭，不得复用快捷摸宝按钮。
