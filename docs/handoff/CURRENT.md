# 当前交接档案 (CURRENT.md)

**更新时间**: 2026-09-07

---

## 当前版本状态

| 项目 | 信息 |
| :--- | :--- |
| **Current version** | `0.4.6` |
| **Latest release** | [`v0.4.6`](https://github.com/zhimaheiye/MaaHappyFish/releases/tag/v0.4.6) |
| **CI hard gate** | `verify (win, x86_64)` PASS（实机 embedded Python 冒烟 + 更新契约门禁） |
| **Release health** | 🟢 **Healthy** — 启用 GitHub 程序内原生整包自动更新 |

**自动更新说明**：v0.4.4 正式引入 `"github": "https://github.com/zhimaheiye/MaaHappyFish"` 字段，为后续程序内原生更新建立 Bootstrap 基础。已安装 v0.4.4 的客户端未来均可直接在 MFA 程序内一键检测并整包升级至最新 Release，无需再次手动解压覆盖。

---

## 已完成功能（Completed）

### 基础挂机功能
- [x] 收鱼产物主干循环（`ResumeHarvest` 万能节点中转）
- [x] 海星定时自动喂食（wall-clock 解耦 Pipeline timeout）
- [x] 巡检收宝（占空比休眠/激活状态机）
- [x] 挂机鱼食预算自动计算与 UI 播报
- [x] 静止画面看门狗（30 秒无变化主动停止）
- [x] MFA UI 日志面板动态播报（`focus` 字段 + `context.override_pipeline`）

### 开贝壳活动 (`OpenShellTask`)
- [x] 多轮开贝壳闭环自动化（需在大章鱼活动主界面启动）
- [x] 结算界面多变体自适应（单按钮居中/双按钮偏右）
- [x] 章鱼保留按钮 OCR 抗分词（`expected: "随机奖品"`）

### 好友摸宝 (`FriendGemTask`)
- [x] 星级好友巡访与金币气泡采集（44 分钟 E2E 实测验证，200 位好友，+597K 金币）
- [x] 双启动入口自适应（好友列表首页 / 任意好友鱼缸就地启动）
- [x] 体力耗尽识别与直通跳过（"刷新体力" OCR $\rightarrow$ `DoNothing` 直通，解耦非必要日志 Action，防止阻断关键导航）
- [x] 统一切好友状态链（`FriendGemNextFriend` $\rightarrow$ `StepFriendGemIndexAction` $\rightarrow$ `ResetFriendGemAttemptsAction`，序号与清零解耦）
- [x] 单帧气泡漏检有界等待机制（`bubble_miss_count`，8 次连续漏检才切好友）
- [x] 误入鱼宝乐园自愈（识别"鱼宝|乐园"，点 X 返回）
- [x] 系统弹窗自动消除（`FriendGemSpecialPopup`，绿色勾选按钮）

### 钓鱼达人 (`FishingTask`)
- [x] 全链路步骤可恢复导航（8 阶段 StartRouter，自身鱼缸 → 游乐园 → 2×6 面板 → 钓场）
- [x] 六地点参数化选择
- [x] 普通鱼饵（黄色奶酪）安全选择，严禁误触蓝色"+"购买入口
- [x] 误入购买弹窗自愈（模板匹配红色×安全关闭）
- [x] 高速咬钩 QTE（~46 FPS 抓帧 + ColorGeometry 1ms 检测，145ms 内响应）
- [x] `max_casts = 5` 双重硬安全上限（Action 层 + Reco 层）

### 海獭摸宝 (`SeaOtterGemTask`)
- [x] 双启动入口自适应（好友列表 / 任意好友鱼缸）
- [x] LEFT/RIGHT 非对称窗口往复摸宝（详见 `docs/features/sea-otter-gem.md`）
- [x] 右侧耗尽退化为 bridge，左侧耗尽才推进窗口
- [x] 连续耗尽自动跳过（防死循环 Safety Limit：30 次连续耗尽触发退出）
- [x] 4 大业务场景 Mock 验证脚本（`dev/test_sea_otter_scenarios.py`）

### 浪漫满屋 (`RomanticHouseTask`)
- [x] 全链路步骤可恢复导航（主鱼缸珊瑚 ➔ 亲吻鱼气泡 ➔ 浪漫满屋主页 ➔ 热恋时刻舞台）
- [x] 动态亲吻鱼气泡识别与 6000ms 鱼群游动遮挡防御等待机制
- [x] 数值状态驱动（点赞值 `10/10` 为唯一完成条件，严禁硬编码情侣鱼名称）
- [x] BlessLoop 拓扑纠正（移除 `on_error` 假分支，建立 CheckDone -> TryBless -> NextCouple 原生回退序列）
- [x] 舞台断点恢复支持（StartRouter 深度优先匹配舞台）与 25 次切对防死循环熔断
- [x] 已祝福状态检测与右箭头顺次切换
- [x] 双级状态驱动安全退出（重制心形关闭模板中心 1197, 57，0.85 阈值，ExitStage ➔ CheckInHome ➔ ExitHome ➔ CheckInFishTank ➔ Done，彻底杜绝 DirectHit 假完成）
- [x] 详细设计文档（`docs/features/romantic-house.md`）


### 发布基础设施
- [x] Windows x64 embedded Python 补齐 `opencv-python-headless`（v0.4.3 patch）
- [x] `agent/requirements-release.txt` 发布依赖清单
- [x] CI `verify (win, x86_64)` 实机 import 冒烟测试硬门禁
- [x] Maa Pipeline 正则静态双层校验（`dev/test_pipeline_regex.py`）
- [x] Pipeline 与 Agent 引用完整性静态门禁（`dev/test_agent_registration_refs.py`）
- [x] GitHub 程序内原生整包自动更新（`interface.json` `github` 字段 + `dev/test_update_contract.py` CI 硬门禁）

---

## 待验证事项 (To Verify)

- [ ] 台式机下载 v0.4.3 正式包，验证 Agent LinkStart 正常（无 cv2 崩溃）
- [ ] 海獭摸宝长循环实机验证（多对好友体力不对称场景）
- [ ] 海獭 NO_TARGET_IN_CURRENT_TANK 短暂提示的完整样本采集

---

## 进行中的工作 (In Progress)

### 🟢 Pipeline 模块化物理拆分 Phase 1（Pipeline Modularization Phase 1）

**状态**: ✅ 已完成模块化拆分与后续金海豚流水线扩展，共 184 节点。

**拆分架构**：
- `assets/resource/pipeline/common/common.json` (5 节点)：应用启动、公告关闭、进游戏、主界面确认、每日签到；
- `assets/resource/pipeline/routine/daily_routine.json` (14 节点)：日常收尾总控调度器、步骤推进、选项开关；
- `assets/resource/pipeline/features/band_fish.json` (31 节点)：乐队鱼演出邀请流水线；
- `assets/resource/pipeline/features/fishing.json` (36 节点)：钓鱼达人全链路导航与垂钓流水线；
- `assets/resource/pipeline/features/golden_dolphin.json` (5 节点)：金海豚导航、游戏、退出与完成流水线；
- `assets/resource/pipeline/features/romantic_house.json` (12 节点)：浪漫满屋双级退出流水线；
- `assets/resource/pipeline/features/friend_gem.json` (22 节点)：好友摸宝巡访流水线；
- `assets/resource/pipeline/features/sea_otter_gem.json` (12 节点)：海獭摸宝流水线；
- `assets/resource/pipeline/features/open_shell.json` (11 节点)：大章鱼开贝壳流水线；
- `assets/resource/pipeline/collect_fish.json` (36 节点)：收鱼主干流水线保持原位；
- 原 `my_task.json` 备份为 `my_task.json.bak`（防 Maa 重复 key 冲突，安全保留回滚途径）。

**验证结果**：
- 当前节点总数：148（模块化业务流水线）+ 36（collect_fish）= 184 节点；
- `Resource.post_bundle("client_avalonia/resource")` 负责全量资源加载验证；
- 物理拆分本身不改变原有路由语义，后续金海豚扩展新增 4 个节点。


### 🟢 DailyRoutineTask v2（日常收尾串行任务容器聚合改造）

**状态**: ✅ 已全量实现并通过 9 项调度器自动化测试与全部静态合规门禁。

**核心能力**：
1. **自由多选组合 (PI V2 Checkbox Option)**：
   - 在 `interface.json` 的 `DailyRoutineTask` 下新增 `日常收尾任务` 多选框，默认全选；
   - 4 个独立的 `DailyRoutineEnable*` 节点接收 `pipeline_override`，支持用户自由勾选任意子集或全选；
2. **串行任务容器与动态队列**：
   - 降级为确定性串行容器，按 `1. 乐队鱼 -> 2. 金海豚 -> 3. 钓鱼达人 -> 4. 浪漫满屋` 严格顺序流转；
   - `advance_daily_routine_step` 动态消耗 `queue`，任务完成或耗尽后顺次推进；
3. **两阶段架构资产保留**：
   - 完整保留乐队鱼 Pass 1 / Pass 2 异步两阶段拓扑节点 (`DailyRoutineStepBandFishPass1`, `DailyRoutineStepBandFishPass2`, `CheckSkip`, `CheckNeeded`) 及相关 Action/Reco，为后续乐队鱼功能打磨完毕后无缝激活预留；
4. **子任务主鱼缸物理归位保证**：
   - 乐队鱼、金海豚、钓鱼达人、浪漫满屋 4 大任务均实现 100% 返回主鱼缸珊瑚确认退出；
5. **独立入口清理**：
   - 已完成验证的 `RomanticHouseTask` 独立入口已从 `interface.json` 移除（统一通过日常收尾调度）；
   - 保留 `BandFishTask`、`GoldenDolphinTask`、`FishingTask` 独立调试入口；
   - 三份 `interface.json`（assets, client, client_avalonia）字节级一致。
6. **门禁与测试验证**：
   - `dev/test_daily_routine_scheduler.py`：9 项组合流转与拓扑测试 100% PASS；
   - 详见 `docs/features/daily-routine.md`。

### 🟢 GoldenDolphinTask（金海豚小游戏 Pipeline 与 Action 接入）

**状态**: ✅ 已正式接入 Pipeline 与 CustomAction。

**已完成能力**：
1. **全链路动作落地**：
   - `GoldenDolphinTaskAction`：导航进入游乐园 $\rightarrow$ 点击金海豚图标 $\rightarrow$ 弹窗几何/语义区分判定 $\rightarrow$ 启动激活点击 $\rightarrow$ Method E XP 收集主循环 $\rightarrow$ 结算退出；
2. **弹窗双模区分机制**：
   - **几何检测**：“想玩小游戏”弹窗左侧伴随红色取消圆形按钮 `(670, 449)`，而“机会耗尽”弹窗无红色按钮；纯离线 OpenCV/NumPy 实现，不引入未打包依赖；
   - **语义检测**：辅助匹配“用完”/“明天再来”；
3. **实机耗尽场景闭环验证**：
   - 实测在次数耗尽场景下，7.1 秒内精准识别弹窗、点击确定关闭并安全返回主鱼缸，沉淀 `NO_STAMINA`。
4. **入口导航安全修复与模板路径统一**：
   - 彻底修复因硬编码遗留目录导致模板对象静默为 `None` 的根因，统一跨环境资源寻址；
   - 关键模板缺失时增加显式 `ERROR` 日志并安全熔断中断，禁止盲目继续；
   - 彻底删除 `(674, 468)` 盲目兜底点击，杜绝在主鱼缸误戳游鱼；
   - 建立严格状态前置门禁：主鱼缸 $\rightarrow$ 模板识别入口点击 $\rightarrow$ 轮询验证游乐园面板展开 $\rightarrow$ 识别金海豚图标 $\rightarrow$ 点击进入；
   - 沉淀《动作前置状态确认规则 (Pre-Action State Verification Rule)》至 `AGENTS.md` 项目硬规则。

### 🟢 BandFishTask（乐队鱼演出）

**状态**: Phase 1（导航与状态识别）、Phase 2（槽位扫描、人机好友纯列表精准定位、防误触高亮选中校验、重进刷新状态机）与 Pass 2（核心演出闭环、乐章确定、4 阶段演出/跳过/结算状态机及调度推进）全量代码落地并 100% 通过全部静态/动态门禁。已完全接入 `DailyRoutineTask`。

**已完成里程碑**：
1. **实机探索取证（Step 1 ~ Step 7）**：
   - 5 槽位映射：槽位 1 不想上课、槽位 2 一只胖梨、槽位 3 麦克（自身）、槽位 4 扶摇、槽位 5 游来游去；
   - 文字 bbox 中心锚点防误邀机制（实测 100% 准确率）；
   - 退出重进自动刷新接受状态（倒计时转为正式名，激活黄色“开始演出”）；
   - 乐章动态探底（向下循环滑动至 diff=0，选取末端最大 Y 坐标，不硬编码曲名）；
   - 25 秒原生水族箱演出（全时段 365 帧 OCR 证实无“跳过”按钮，演出不可跳过）；
   - 自动结算到账（+10,000 金币、+1,500 鱼食）；
   - 体力耗尽防线：结算后原按钮被替换为“12💎返场演出”（0/2），识别此特征立即安全退出。
2. **Phase 1 代码落地与门禁验证**：
   - `assets/resource/pipeline/features/band_fish.json`：新增 `BandFishTask`、`BandFishStartRouter`（Deepest-first 步骤可恢复：已在我的演出 / 在游乐园面板 / 在鱼缸主界面）及 `BandFishStatusRouter`；
   - `agent/runtime_state.py`：新增 `band_fish_state` 与 `BAND_FISH_TARGETS`；
   - `agent/my_action.py`：新增 `InitBandFishStateAction`、`LogBandFishStatusAction`；
   - `assets/resource/image/乐队鱼_图标.png`：添加 60×60 模板图标；
   - `interface.json`：三份完全同步并通过 `test_update_contract.py`；
   - `test_pipeline_regex.py`、`test_agent_registration_refs.py` 静态门禁 100% 通过；
   - 实机动态多阶段启动测试 100% 通过。
3. **Phase 2 邀请与防误触闭环全量落地**：
   - `agent/runtime_state.py`：槽位 1、2、4、5 状态跟踪器就绪；
   - `agent/my_reco.py`：`CheckBandFishReadyReco`、4 槽位 `CheckBandFishNeedSlot*Reco`、`CheckBandFishNeedRefreshReco` 就绪；
   - `agent/my_action.py`：`BandFishScanSlotsAction`（Native OCR 槽位多模态识别）、`BandFishInviteSlotAction`（文字中心锚点定位、Diff 选中校验防误触、底栏邀请点击）、`BandFishRefreshStateAction`（退出重进触发 Bot 接受刷新）；
   - 全套门禁（Regex、Refs、Update Contract、Embedded Imports、Reco 单元测试）100% PASS。
4. **Pass 2 演出闭环与跳过前置架构整理**：
   - `BandFishPerformAction` 内部职责清晰化（开始演出、选曲确认、演出与跳过检测、结算等待与领取、状态沉淀）；
   - 4 阶段状态机（`PLAYING -> WAIT_SKIP_BUTTON -> CLICK_SKIP -> WAIT_RESULT`）；
   - 预留跳过接口与模板加载契约（`check_band_fish_skip_button` / `load_band_fish_skip_template`），默认安全空实现无盲点；
   - 离线测试套件（`dev/test_daily_routine_suite.py` Test 10）全面覆盖接口契约、默认无跳过流转与 Mock 跳过流转。
5. **⚠️ 2026-09-06 业务事故与重大纠偏（必须执行）**：
   - **事故**: 动态全槽位邀请重构中，误将“解耦硬编码坐标”延伸为“移除目标好友名字校验，遍历首项卡片直接邀请”，导致对非人机好友发出了邀请。
   - **纠偏规范（纯列表 OCR 方案）**: 4 位人机好友（`不想上课`、`一只胖梨`、`扶摇`、`游来游去`）具备秒级接受特性，是自动化闭环的基石，硬编码好友名字是业务刚需。必须严格执行纯列表 OCR 方案：打开好友页面 -> 列表 OCR 提取名字 -> 与 `BAND_FISH_TARGETS` 精确匹配 -> 命中中心点击 -> 选中核验（高亮+底栏变绿） -> 确认提交。**彻底删除搜索栏方案，严禁使用搜索框，严禁点击列表首项，严禁根据排序猜测，严禁根据坐标固定绑定好友**。

**后续规划（Phase 3）**：
- 在未来采集到真实跳过按钮样本时，直接在 `check_band_fish_skip_button` 内部启用模板匹配，无需再动整体状态机结构。

### 🟡 GoldenDolphinTask（金海豚小游戏）

**状态**: Phase 1.5（全量 Benchmark 验证）与 Phase 2A（启动机制关键发现）已完成；今日游戏次数耗尽，功能暂停开发。

**重大机制发现（Hidden Trigger Mechanism）**：
- **进入小游戏后不是立即开始正式计时，存在隐藏启动状态**：
  ```
  进入小游戏
      ↓
  等待玩家首次点击 [GoldenDolphinWaitingStart]
      ↓
  正式开始计时 (30.0s 倒计时开始)
  ```
- **未点击时**：
  - 只掉落初始金币；
  - 不出现 XP/爱心等奖励；
  - XP 检测算法不会有任何检出结果。
- **正式状态机设计硬契约**：
  - 必须包含 `GoldenDolphinWaitingStart` 状态节点；
  - 在该状态下严禁执行 XP 目标检测；
  - 必须先完成一次启动点击/激活验证。

**视觉与物理适配已就绪基础**：
- **算法就绪**：Method E（HSV 粗筛 + 几何硬过滤 + 局部微补丁模板确认）已验证：准确率 92.4%，召回率 97.5%，耗时 33ms，金币负样本 0 误检；
- **物理坐标映射**：MuMu 模拟器物理为 1080p ($1920\times1080$)，截图为 720p ($1280\times720$)，ADB 点击坐标需缩放 $1.5$ 倍；
- **全链路资产**：游乐园入口、金海豚图标、确定按钮、经验星、结束取消按钮模板均已提取完备；
- **详细功能文档**：见 `docs/features/golden-dolphin.md`。

**后续复工待确认事项（To Verify when resuming）**：
1. 任意位置点击是否可以启动小游戏倒计时；
2. 是否必须点击金币才激活启动；
3. 启动后多久进入 XP 掉落阶段。

---

## 已知问题与限制

### 海獭 NO_TARGET_IN_CURRENT_TANK（待处理）

进入某些好友鱼缸时游戏会显示"这个鱼缸没有可以摸取……"等短暂提示（约 1~2 秒自动消失）。当前版本未处理该状态，不实现好友内部换缸。详见 `docs/features/sea-otter-gem.md`。

---

## 暂不实现区域 (Non-Goals)

- 鱼苗养殖自动化（范围外）
- 宝石兑换逻辑（范围外）
- 任何涉及氪金/付费的点击（**项目级严禁**）

---

## 交接备忘 (Handoff Notes)

### 关键文件同步规范
`interface.json` 改动后，**务必**手动分发覆盖 `assets/`、`client_avalonia/` 和 `client/` 三处（junction link 仅覆盖 resource 文件夹）。

### Agent 排查第一步
调试遇到 Agent 无故终止时，第一时间检查：
1. 是否有新代码在 Python `print()` 中使用了 Emoji（GBK 崩溃）
2. 发行包是否缺少第三方依赖（参见 Release Runtime Dependency Rule in AGENTS.md）

### UI 日志面板原理
MFA UI 日志面板的内容来源是 Pipeline `focus` 字段触发的框架回调，**不是** Python `print()`。如需在 UI 显示动态消息，在 Python Agent 中调用 `context.override_pipeline()` 注入目标节点的 `focus` 内容。

### 步骤可恢复导航
存在多步流程的任务必须实现 StartRouter，最深已知阶段优先自适应恢复。各阶段契约在各 feature 文档中明确记录。

### 发行包依赖
新增任何第三方 `import` 前，必须同步更新 `agent/requirements-release.txt` 并通过 `dev/test_release_agent_imports.py` 验证。
