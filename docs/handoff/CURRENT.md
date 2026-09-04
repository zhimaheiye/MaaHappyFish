# 当前交接档案 (CURRENT.md)

**更新时间**: 2026-09-04

---

## 当前版本状态

| 项目 | 信息 |
| :--- | :--- |
| **Current version** | `0.4.3` |
| **Latest release** | [`v0.4.3`](https://github.com/zhimaheiye/MaaHappyFish/releases/tag/v0.4.3)（已正式发布） |
| **Latest main commit** | `a2bda27` (`chore(release): bump version to v0.4.3`) |
| **CI hard gate** | `verify (win, x86_64)` PASS（实机 embedded Python import 冒烟测试通过） |
| **Release health** | 🟢 **Healthy** — 8 平台构建全部成功，Windows x64 实机验证通过，Release 资产已发布 |

**重要 patch 背景**：v0.4.2 Windows x64 发行包存在 Agent 启动时 `import cv2` 失败导致无法 LinkStart 的严重故障（根因：发行包 embedded Python 缺少 `opencv-python-headless`）。v0.4.3 已彻底修复并建立 CI 实机硬门禁。

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

### 发布基础设施
- [x] Windows x64 embedded Python 补齐 `opencv-python-headless`（v0.4.3 patch）
- [x] `agent/requirements-release.txt` 发布依赖清单
- [x] CI `verify (win, x86_64)` 实机 import 冒烟测试硬门禁
- [x] Maa Pipeline 正则静态双层校验（`dev/test_pipeline_regex.py`）
- [x] Pipeline 与 Agent 引用完整性静态门禁（`dev/test_agent_registration_refs.py`）

---

## 待验证事项 (To Verify)

- [ ] 台式机下载 v0.4.3 正式包，验证 Agent LinkStart 正常（无 cv2 崩溃）
- [ ] 海獭摸宝长循环实机验证（多对好友体力不对称场景）
- [ ] 海獭 NO_TARGET_IN_CURRENT_TANK 短暂提示的完整样本采集

---

## 暂停中的工作 (Paused / Next Planned)

### 🔴 BandFishPerformanceTask（乐队鱼演出）

**状态**: 需求已确认，**开发尚未开始（0 行代码）**。本地无任何 BandFish 实现文件。

**暂停原因**: 开发进行到一半时，优先处理了 v0.4.2 发行包 cv2 故障（v0.4.3 修复），完成后统一文档收口。

**已知业务流程**（用户描述，未实机验证）：

1. 自身鱼缸 → 游乐园（摩天轮）
2. 2×6 活动面板 → **第一排第 6 个入口**（乐队鱼）
3. 乐队鱼准备页
4. 邀请固定 4 个官方好友（不想上课 / 一只胖梨 / 扶摇 / 游来游去）
5. 等待好友异步同意（需退出/重新进入循环检查）
6. 出现「开始演出」按钮 → 点击
7. 乐谱列表滑动到最下方 → 选择目标乐谱 → 开始演出
8. 演出中点击「跳过」
9. 完成

**关键红线**：
- "麦克"是用户自己，**绝对不要邀请**
- "返场演出"按钮不属于当前功能，**绝对不要点击**
- 每天只有 1 次演出体力，在点击「开始演出」时消耗，**属于稀缺资源**

**正式开发必须按稀缺资源分阶段模式进行**（参见 AGENTS.md 相关规则）。

**当前断点**: Step 0 — 尚未开始任何 Step 1 探索。

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
