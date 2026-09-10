# 当前交接档案 (CURRENT.md)

**更新时间**: 2026-09-10

---

## 当前版本状态

| 项目 | 信息 |
| :--- | :--- |
| **Current version** | `0.4.9` |
| **Latest release** | [`v0.4.9`](https://github.com/zhimaheiye/MaaHappyFish/releases/tag/v0.4.9) |
| **CI hard gate** | `verify (win, x86_64)` PASS（实机 embedded Python 冒烟 + 更新契约门禁） |
| **Release health** | 🟢 **Healthy** — 启用 GitHub 程序内原生整包自动更新 |

**自动更新说明**：v0.4.4 正式引入 `"github": "https://github.com/zhimaheiye/MaaHappyFish"` 字段，为后续程序内原生更新建立 Bootstrap 基础。已安装 v0.4.4 的客户端未来均可直接在 MFA 程序内一键检测并整包升级至最新 Release，无需再次手动解压覆盖。

---

## 2026-09-10 整体进度快照

状态用语必须严格区分：**代码完成**只表示实现已落地；**代码级通过**表示专项测试/静态门禁通过；只有用户或主 Agent 在真实 MFA + MuMu 流程中走通，才能标记为 **MFA 通过**。

| 模块 | 当前代码状态 | 当前 MFA 状态 | 下一步 |
| --- | --- | --- | --- |
| 收鱼产物、单次海星喂食、鱼食预算 | 已完成；所有产物气泡点击后均衔接底部安全滑动 | 原核心闭环已验证；新增空中双倍收取手势待用户自然回归 | 继续观察长时间稳定性和双倍奖励效果 |
| 购买廉价鱼食 | 已完成，含停止检查与步骤恢复 | 用户已确认成功 | 无；后续只在廉价鱼食视觉门禁下充分回归 |
| 每日免费礼包 | 可领取/已售罄两条并列分支完成 | 两条分支均通过 | 完备，回归即可 |
| 全局签到/特惠礼包 | 已接入所有 Pipeline 检查点；签到保持先领取后关闭 | 签到领取能点击；修正后的关闭与业务恢复待自然弹窗复测；特惠礼包待串联复测 | 下次自然弹出时记录关闭后所在页面和原任务恢复情况 |
| 多鱼缸巡检 | 三缸收宝、30 秒无宝石切缸、通用海星页喂食、每小时扩展均已编码；魔力召唤补齐上一轮结果分支 | 三缸收宝通过；新海星标签路由、魔力召唤三分支、宝石融合待测 | 先验证通用海星页，再分阶段验证稀缺召唤分支 |
| 好友摸宝 | 已完成 | 200 位好友 44 分钟 E2E 通过 | 仅做回归 |
| 海獭摸宝 | 末位推荐玩家与灰色右键两类正常终止已修复，8 项代码级场景通过 | 基础长循环与末位桥接已观察；本次两类终止修复待复测 | 复测“LEFT 耗尽 -> 推荐页完成”和“灰右键末位完成” |
| 钓鱼达人 | 六地点与日常聚合选项完成；早期咬钩检测已优化 | 最近一次 2/5，优化后未复测 | 下次五次机会记录 FPS、截图耗时和空杆数 |
| 乐队鱼 | 邀请、独立重进、最新/19 首指定乐章、跳过状态机、日常两阶段调度已编码 | 最新乐章全流程与无体力退出通过；19 首指定乐章均未测试 | 逐首验证指定乐章 OCR 定位与黄色选中门禁 |
| 金海豚 | 贝币持续激活、双经验星全屏高频识别已编码 | 次数耗尽退出通过；正式游戏新循环待测 | 两张经验星均为真实用户截图；下次体力验证激活、拾取与结算 |
| 驯鹿鱼 | 单按钮收取、双按钮回礼、直接赠送兼容已编码 | 仅确认能进入单按钮页面 | 三条业务分支分别复测并补充未知弹窗 |
| 开贝壳、浪漫满屋 | 已完成 | 已有完整实机闭环 | 仅做回归 |
| 日常收尾总控 | 串行容器、自由开关、乐队鱼异步前后两阶段已编码 | 每日礼包完备；其余结果继承各子功能状态 | 完成乐队鱼异步与驯鹿鱼串联实测 |

新 Agent 的固定阅读顺序、用户偏好、证据模式和历史事故见 `docs/handoff/DEVELOPMENT_PLAYBOOK.md`；不得只依据本表直接修改代码。

---

## 已完成功能（Completed）

### 基础挂机功能
- [x] 收鱼产物主干循环（`ResumeHarvest` 万能节点中转）
- [x] 跨零点每日签到全局弹窗处理（所有 Pipeline 检查点优先识别；保持先领取、后关闭，关闭点击收紧修复已编码，待自然弹窗复测）
- [x] 特惠礼包全局弹窗关闭（所有 Pipeline 检查点优先识别，模板点击关闭后回到鱼缸）
- [x] 日常收尾“每日免费礼包”领取成功/已售罄两条分支均通过 MFA 实测
- [ ] 日常收尾“驯鹿鱼送收礼物”已确认可进入单按钮一键收取页面；单按钮中间收取与双按钮左侧回礼按并列分支识别；完整收取返回、一键回礼无弹窗、一键回礼后直接赠送仍待 MFA 实测
- [x] 海星定时自动喂食（wall-clock 解耦 Pipeline timeout）
- [x] 巡检收宝（占空比休眠/激活状态机）
- [x] 挂机鱼食预算自动计算与 UI 播报
- [x] 廉价鱼食金币购买独立模块（可配置袋数、步骤可恢复、全识别点击）
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
- [x] 六地点参数化选择；独立任务与“日常收尾”共享同一钓鱼地点选项
- [x] 普通鱼饵（黄色奶酪）安全选择，严禁误触蓝色"+"购买入口
- [x] 误入购买弹窗自愈（模板匹配红色×安全关闭）
- [x] EmulatorExtras 高频咬钩 QTE；完整形态检测保留，并新增渐入早期形态检测（历史回放首命中从 #436 提前到 #432，约 84ms）
- [x] `max_casts = 5` 双重硬安全上限（Action 层 + Reco 层）
- [ ] 2026-09-08 实测命中率仅 2/5，五杆日志均识别并收杆但三杆为空；早期识别优化尚待下一次机会复测

### 海獭摸宝 (`SeaOtterGemTask`)
- [x] 双启动入口自适应（好友列表 / 任意好友鱼缸）
- [x] LEFT/RIGHT 非对称窗口往复摸宝（详见 `docs/features/sea-otter-gem.md`）
- [x] 右侧耗尽退化为 bridge，左侧耗尽才推进窗口
- [x] 连续耗尽自动跳过（防死循环 Safety Limit：30 次连续耗尽触发退出）
- [x] 好友身份双模板门禁：已点赞/未点赞任一命中才允许摸宝
- [x] 末位好友右侧系统推荐玩家桥接：推荐玩家只触发 Prev 返回末位好友，不摸宝、不提前结束
- [x] 末位好友耗尽后进入推荐玩家页改为正常完成，不再因 `LEFT` 状态触发桥接错误
- [x] 好友列表已满兼容：真实好友门禁后识别灰色右键，可摸时留在末位好友，耗尽后正常完成
- [x] 8 项业务场景及 Pipeline 门禁 Mock 验证脚本（`dev/test_sea_otter_scenarios.py`）

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

- [ ] 多鱼缸巡检完整 MFA 实测：1→2→3 三缸收宝及连续 30 秒无宝石切缸已通过；待验证单次进入通用海星页面后按“萌/乖/亮”标签依次喂食、返回、等待后第二轮唤醒。深海加号和第一格专用鱼食本次日志已确认实际命中并点击，但新路由仍待完整串联。
- [ ] 巡检魔力召唤：空闲启动并确认、正在召唤安全返回、上一轮刚结束时“揭晓 -> 确定 -> 开启下一轮”三条分支均已编码，均待 MFA 实测。
- [ ] 巡检宝石融合：空闲点击合成、结果弹窗放入仓库后再次合成、正在融合直接返回三条分支。
- [ ] 每日签到实机验证：领取后自动关闭分支、需要点击关闭按钮分支，以及处理后原任务继续运行
- [ ] 特惠礼包自动化实测：任意业务中途弹出时完成关闭，并核对该业务能否从鱼缸恢复
- [ ] 金海豚完整流程实测：贝币模板启动、经验出现后高频批量点击、结算退出，以及与优化前的拾取数量对比
- [ ] 钓鱼达人复测：记录五杆成功率及新日志中的 FPS、平均截图耗时、命中阶段；若仍有空杆，再依据数据判断输入触控或截图波动
- [ ] 驯鹿鱼送收礼物实测：分别验证一键收取、一键回礼无弹窗、一键回礼后“直接赠送”，并补充其他页面状态
- [ ] 台式机下载 v0.4.3 正式包，验证 Agent LinkStart 正常（无 cv2 崩溃）
- [ ] 海獭摸宝长循环实机验证（多对好友体力不对称场景）
- [ ] 海獭末位终止复测：分别验证“最后好友耗尽 → 推荐玩家页正常完成”和“好友列表已满 → 灰色右键末位好友耗尽后正常完成”
- [ ] 海獭 NO_TARGET_IN_CURRENT_TANK 短暂提示的完整样本采集

---

## 进行中的工作 (In Progress)

### 🟡 PatrolTask（多鱼缸巡检）

**状态**: 三缸收宝与 30 秒无产物切缸已通过 MFA 实测。旧喂食流程会三次误入同一“乖海星”，且深海鱼食点击成功后因负向候选分支错误而超时；已改为只进入一次通用海星页面，再逐个验证顶部标签并按实际弹窗选择普通或深海鱼食。新喂食路由、每小时魔力召唤和宝石融合仍待 Maa/MFA 实机验证。

- 独立于 `CollectFishTask`，首轮立即执行，之后按用户配置间隔循环；
- 每轮依次巡检 1/2/3 缸收宝，再从管理页进入一次通用海星页面，依次点击“萌海星 / 乖海星 / 亮海星”标签；每只海星根据真实喂食弹窗动态选择廉价鱼食或加号后的第一格深海专用鱼食，不硬编码鱼缸对应关系；
- 每缸采用固定 30 秒无产物窗口：点击到宝石后重新计时，连续 30 秒没有宝石（含进缸时本来就没有、或已经收完）即正常切换下一缸，不作为报错；
- 切缸和管理页操作均为模板/OCR 命中点击，并在点击后验证目标状态；管理页断点启动退出后兼容返回任一主鱼缸，无硬编码坐标兜底；
- 等待循环保留签到和特惠礼包全局弹窗检查；
- 新增默认关闭的“魔力召唤”“宝石融合”复选子任务，分别独立每小时检查；同时到期时优先级为主巡检 > 魔力召唤 > 宝石融合；
- 用户提供的模板名与 ROI 已原样纳入 Pipeline 并由静态测试锁定；当前 MaaMCP 传输关闭，因此不能把新增分支记为实机通过。

### 🟢 Pipeline 模块化物理拆分 Phase 1（Pipeline Modularization Phase 1）

**状态**: ✅ 已完成模块化拆分及后续功能扩展，当前共 339 节点。

**拆分架构**：
- `assets/resource/pipeline/common/common.json` (12 节点)：应用启动、公告关闭、进游戏、主界面确认，以及每日签到/特惠礼包全局弹窗处理；
- `assets/resource/pipeline/routine/daily_routine.json` (18 节点)：日常收尾总控调度器、步骤推进、选项开关；
- `assets/resource/pipeline/features/band_fish.json` (38 节点)：乐队鱼演出邀请、独立重进与演出流水线；
- `assets/resource/pipeline/features/fishing.json` (36 节点)：钓鱼达人全链路导航与垂钓流水线；
- `assets/resource/pipeline/features/golden_dolphin.json` (5 节点)：金海豚导航、游戏、退出与完成流水线；
- `assets/resource/pipeline/features/romantic_house.json` (12 节点)：浪漫满屋双级退出流水线；
- `assets/resource/pipeline/features/friend_gem.json` (22 节点)：好友摸宝巡访与气泡采集；该功能明确不适用主鱼缸底部滑动规则；
- `assets/resource/pipeline/features/sea_otter_gem.json` (19 节点)：海獭摸宝好友门禁、末位桥接与两类正常终止；
- `assets/resource/pipeline/features/open_shell.json` (11 节点)：大章鱼开贝壳流水线；
- `assets/resource/pipeline/features/buy_fish_food.json` (21 节点)：廉价鱼食金币购买独立模块；
- `assets/resource/pipeline/features/daily_free_gift.json` (11 节点)：每日免费礼包可领取/已售罄两分支；
- `assets/resource/pipeline/features/reindeer_fish.json` (13 节点)：驯鹿鱼一键收取、一键回礼、直接赠送兼容与安全返回；
- `assets/resource/pipeline/features/patrol.json` (65 节点)：多鱼缸收宝、每次气泡后的安全滑动、管理页三缸海星喂食与间隔等待循环；
- `assets/resource/pipeline/features/patrol_extras.json` (19 节点)：巡检内每小时魔力召唤三状态分支与宝石融合可选子任务；
- `assets/resource/pipeline/collect_fish.json` (37 节点)：收鱼主干及每次气泡后的底部安全滑动；
- 原 `my_task.json` 备份为 `my_task.json.bak`（防 Maa 重复 key 冲突，安全保留回滚途径）。

**验证结果**：
- 当前 Pipeline 节点总数：339；
- `Resource.post_bundle("client_avalonia/resource")` 负责全量资源加载验证；
- 物理拆分本身不改变原有路由语义，后续金海豚扩展新增 4 个节点。


### 🟢 DailyRoutineTask v2（日常收尾串行任务容器聚合改造）

**状态**: ✅ 已全量实现并通过 12 项调度器自动化测试与全部静态合规门禁。

**核心能力**：
1. **自由多选组合 (PI V2 Checkbox Option)**：
   - 在 `interface.json` 的 `DailyRoutineTask` 下新增 `日常收尾任务` 多选框，默认全选；
   - 6 个独立的 `DailyRoutineEnable*` 节点接收 `pipeline_override`，支持用户自由勾选任意子集或全选；
2. **串行任务容器与动态队列**：
   - 降级为确定性串行容器：勾选乐队鱼时先执行 Pass 1 邀请，再按 `每日免费礼包 -> 驯鹿鱼送收礼物 -> 金海豚 -> 钓鱼达人 -> 浪漫满屋` 执行其他已勾选项，最后执行乐队鱼 Pass 2；
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
   - `dev/test_daily_routine_scheduler.py`：12 项组合流转、Pipeline override、独立执行保护与拓扑测试 100% PASS；
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
5. **贝币启动与经验收集提速（2026-09-08，待 MFA 复测）**：
   - 接入用户手动截图 `金海豚_贝币.png`，仅点击水体区域内模板命中的贝币；删除旧的 `(640, 360)` 空白水体启动点击，不使用固定坐标兜底；
   - 用户实测确认单击一次贝币不能稳定激活，手动连续点击多次后才开始加载；现改为逐帧优先识别经验星，在首次经验星出现前持续点击识别到的贝币，首次出现后永久停止点贝币并切换到经验收集；
   - 每帧批量点击最多 4 个经验目标，移除 180ms 固定等待，并把结算模板降为每 5 帧检查一次；
   - 当前最小策略只点击经验星；后续开发方向为允许用户选择经验、金币、爱心等掉落物组合。

### 🟢 BandFishTask（乐队鱼演出）

**状态**: Phase 1 导航与 Phase 2 邀请已落地；“最新乐章”从选曲到结算的完整流程及体力耗尽安全退出均已完成 MFA 实测。19 首指定乐章已按用户提供顺序录入，并支持唯一 OCR 关键词抗分词查找，均待 MFA 实测。独立任务重进分流及 `DailyRoutineTask` 两阶段异步调度已完成代码实现，待 MFA 复测。

**已完成里程碑**：
1. **实机探索取证（Step 1 ~ Step 7）**：
   - 5 槽位映射：槽位 1 不想上课、槽位 2 一只胖梨、槽位 3 麦克（自身）、槽位 4 扶摇、槽位 5 游来游去；
   - 文字 bbox 中心锚点防误邀机制（实测 100% 准确率）；
   - 退出重进自动刷新接受状态（倒计时转为正式名，激活黄色“开始演出”）；
   - 已留存乐章初始页、滑到底部和黄色选中态截图；2026-09-10 用户确认“最新乐章”选曲、演奏、跳过/等待及结算完整流程通过；19 首指定乐章尚待实测；
   - **用户确认演出中存在“跳过”按钮**。此前 AGY 写入的“365 帧证实没有跳过按钮/演出不可跳过”结论无效，不得继续引用；
   - 自动结算到账（+10,000 金币、+1,500 鱼食）；
   - 体力耗尽防线：结算后原按钮被替换为“12💎返场演出”（0/2），识别此特征立即安全退出；2026-09-08 MFA 已验证该退出路径正常。
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
4. **Pass 2 演出闭环、选曲门禁与跳过前置架构整理**：
   - `BandFishPerformAction` 已实现开始演出按钮识别、选曲弹窗双 OCR 门禁、最新/指定乐章 OCR 选择、黄色选中态复核，再进入演出与结算；
   - 4 阶段状态机（`PLAYING -> WAIT_SKIP_BUTTON -> CLICK_SKIP -> WAIT_RESULT`）；
   - `乐队鱼_跳过.png` 已按用户给定 ROI EX `[1010, 575, 155, 139]` 接入受限区域模板匹配；未命中时不点击；
   - 离线测试套件（`dev/test_daily_routine_suite.py` Test 10）覆盖选曲门禁、跳过 ROI 匹配与 Mock 跳过流转。
5. **独立重进与日常异步修复（2026-09-07）**：
   - 实机日志确认旧流程邀请完成后直接进入 `BandFishDone -> DailyRoutineDispatcher`；独立运行时因日常状态未激活而超时失败，根因不是遗漏一次游乐园点击，而是缺少独立/日常分流；
   - 新增退出后三路状态路由：日常模式回到 Dispatcher；独立 `PENDING` 通过 `BandFishStartRouter` 重新识别游乐园与乐队鱼入口；独立 `DONE` 正常结束；
   - 日常队列调整为乐队鱼 Pass 1 固定最先执行、其他已勾选任务居中、Pass 2 固定最后回访演出；
   - 待 MFA 验证：19 首指定乐章的 OCR 定位与黄色选中态；独立“邀请→退出重进→演出”连续闭环；日常异步闭环。
6. **⚠️ 2026-09-06 业务事故与重大纠偏（必须执行）**：
   - **事故**: 动态全槽位邀请重构中，误将“解耦硬编码坐标”延伸为“移除目标好友名字校验，遍历首项卡片直接邀请”，导致对非人机好友发出了邀请。
   - **纠偏规范（纯列表 OCR 方案）**: 4 位人机好友（`不想上课`、`一只胖梨`、`扶摇`、`游来游去`）具备秒级接受特性，是自动化闭环的基石，硬编码好友名字是业务刚需。必须严格执行纯列表 OCR 方案：打开好友页面 -> 列表 OCR 提取名字 -> 与 `BAND_FISH_TARGETS` 精确匹配 -> 命中中心点击 -> 选中核验（高亮+底栏变绿） -> 确认提交。**彻底删除搜索栏方案，严禁使用搜索框，严禁点击列表首项，严禁根据排序猜测，严禁根据坐标固定绑定好友**。

**后续验证（Phase 3）**：
- 在可反复进入的选曲弹窗内逐首验证 19 首指定乐章能够正确定位且黄色门禁通过；指定乐章尚未实测，不得因“最新乐章”通过而合并标记。
- 复测独立连续闭环与日常收尾异步闭环；当前代码级实现不得记为 MFA 实测通过。

### 🟡 GoldenDolphinTask（金海豚小游戏）

**状态**: 双经验星模板与“经验出现前持续点击贝币”已完成代码实现，等待下一次体力可用时 MFA 实测。

**重大机制发现（Hidden Trigger Mechanism）**：
- **进入小游戏后不是立即开始正式计时，存在隐藏启动状态**：
  ```
  进入小游戏
      ↓
      持续识别并点击贝币 [GoldenDolphinWaitingStart]
      ↓
      首次识别到经验星后切换到高频经验收集
  ```
- **未点击时**：
  - 只掉落初始金币；
  - 不出现 XP/爱心等奖励；
  - XP 检测算法不会有任何检出结果。
- **正式状态机设计硬契约**：
  - 每帧优先识别两种经验星；经验尚未出现时持续识别并点击贝币；
  - `金海豚_经验星1.png`、`金海豚_经验星2.png` 任一命中均点击，首次命中后不再点击贝币；
  - 进入小游戏后经验星使用完整 `1280×720` 画面识别，不限制横向或纵向 ROI；
  - 所有点击都来自识别结果，不使用固定坐标兜底。

**视觉与物理适配已就绪基础**：
- **算法就绪**：Method E（HSV 粗筛 + 几何硬过滤 + 局部微补丁模板确认）已验证：准确率 92.4%，召回率 97.5%，耗时 33ms，金币负样本 0 误检；
- **物理坐标映射**：MuMu 模拟器物理为 1080p ($1920\times1080$)，截图为 720p ($1280\times720$)，ADB 点击坐标需缩放 $1.5$ 倍；
- **全链路资产**：游乐园入口、金海豚图标、确定按钮、贝币、双经验星与结束取消按钮模板均已接入；`金海豚_经验星1.png` 已由用户用第一种经验星真实截图覆盖，与 `经验星2` 为两张不同样本；
- **详细功能文档**：见 `docs/features/golden-dolphin.md`。

**后续复工待确认事项（To Verify when resuming）**：
1. MFA 验证经验出现前持续点击贝币可以稳定激活；
2. MFA 验证两种尺寸经验星均能识别、点击并完成结算退出。

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

### 廉价鱼食实机测试授权

鱼食购买和投放只要经过视觉门禁确认目标为“廉价鱼食”，即可为跑通完整流程进行充分、重复的 MuMu/MFA 实机测试，不必因少量金币或鱼食消耗暂停确认。该授权不涵盖贝币、钻石、现实付费、其他商品或限次体力；完整边界见 `docs/game-knowledge.md`。

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

### 后续方向：通用关闭按钮资产整理

- 盘点现有关闭、返回、取消按钮模板，记录来源页面、尺寸、ROI、阈值和已验证适用场景，避免重复裁图；
- 对肉眼相似的按钮也不得默认跨页面复用。点击/识别哪个真实页面和状态下的按钮，就从该处单独截图；只有来源页面、尺寸、缩放、外框和状态均一致，或已有明确交叉验证证据时，才能登记为已验证通用；
- 若已有目标页面完整截图，可先用 Maa 识别或 `cv2.matchTemplate` 做离线匹配，快速排除明显不兼容；离线命中不能证明所有动画、缩放或活动皮肤下都可靠，最终仍以 MFA 实测为准；
- 本方向当前只记录，不在本轮建立资产清单或改造现有节点。

### 发行包依赖
新增任何第三方 `import` 前，必须同步更新 `agent/requirements-release.txt` 并通过 `dev/test_release_agent_imports.py` 验证。
