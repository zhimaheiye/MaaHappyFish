# 当前交接档案 (CURRENT.md)

**更新时间**: 2026-09-04

---

## 当前版本状态

| 项目 | 信息 |
| :--- | :--- |
| **Current version** | `0.4.4` |
| **Latest release** | [`v0.4.4`](https://github.com/zhimaheiye/MaaHappyFish/releases/tag/v0.4.4)（准备发布） |
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
- [x] 已祝福状态检测与右箭头顺次切换
- [x] 双级安全退出（`0.55` 容错阈值匹配关闭小叉号，舞台 ➔ 主页 ➔ 主鱼缸）
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

### 🟡 BandFishTask（乐队鱼演出）

**状态**: Phase 1（导航与状态识别）与 Phase 2（槽位扫描、好友搜索定位、防误触高亮选中校验、重进刷新状态机）全量代码落地并 100% 通过全部静态/动态门禁。

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
   - `assets/resource/pipeline/my_task.json`：新增 `BandFishTask`、`BandFishStartRouter`（Deepest-first 步骤可恢复：已在我的演出 / 在游乐园面板 / 在鱼缸主界面）及 `BandFishStatusRouter`；
   - `agent/runtime_state.py`：新增 `band_fish_state` 与 `BAND_FISH_TARGETS`；
   - `agent/my_action.py`：新增 `InitBandFishStateAction`、`LogBandFishStatusAction`；
   - `assets/resource/image/乐队鱼_图标.png`：添加 60×60 模板图标；
   - `interface.json`：三份完全同步并通过 `test_update_contract.py`；
   - `test_pipeline_regex.py`、`test_agent_registration_refs.py` 静态门禁 100% 通过；
   - 实机动态多阶段启动测试 100% 通过。
3. **Phase 2 邀请与防误触闭环全量落地**：
   - `agent/runtime_state.py`：槽位 1、2、4、5 状态跟踪器就绪；
   - `agent/my_reco.py`：`CheckBandFishReadyReco`、4 槽位 `CheckBandFishNeedSlot*Reco`、`CheckBandFishNeedRefreshReco` 就绪；
   - `agent/my_action.py`：`BandFishScanSlotsAction`（Native OCR 槽位多模态识别）、`BandFishInviteSlotAction`（搜索框输入、文字中心锚点定位、Diff 选中校验防误触、底栏邀请点击）、`BandFishRefreshStateAction`（退出重进触发 Bot 接受刷新）；
   - `assets/resource/pipeline/my_task.json`：挂接 `BandFishScanSlots`、`BandFishInviteLoopRouter`、4 槽位邀请分支、刷新桥梁与辅助识别节点；
   - 全套门禁（Regex、Refs、Update Contract、Embedded Imports、Reco 单元测试）100% PASS。

**后续规划（Phase 3）**：
- 动态遍历乐章列表到底部选取最新乐曲并确认开启演出（需在每日体力充足且准备消耗时实机测试）。


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
