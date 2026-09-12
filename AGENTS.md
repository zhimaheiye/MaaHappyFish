# MaaHappyFish 导航地图 (AGENTS.md)

## 项目概述
开心水族箱挂机小助手（MaaHappyFish）是一个基于 MaaFramework 和 Python Agent 的自动化黑盒测试工具，专为 MuMu 模拟器环境设计，提供收鱼、定时喂海星、挂机巡检等自动化辅助功能，并附带 MFAAvalonia 桌面 UI。

## 开发环境启动命令
- **设备要求**: MuMu 模拟器 v5+ (adb connect 127.0.0.1:16416)
- **运行客户端**: 运行 `client_avalonia/` 下的 MFAAvalonia 客户端程序。
- **独立计算器**: `python tools/fish_food_calculator.py`

## 文档路由表
| 遇到问题 | 查阅文档 |
| --- | --- |
| 需了解整体架构或边界约束 | `PRODUCT.md` |
| 查看当前正式版与机器运行状态 | `PROJECT_STATUS.md` |
| 查看或登记待修复问题 | `ISSUES.md` |
| 接手当前工作或查看进度 | `docs/handoff/CURRENT.md` |
| 新 Agent 接手、查询开发流程/用户偏好/历史事故 | `docs/handoff/DEVELOPMENT_PLAYBOOK.md` |
| 查询游戏资源、消耗与实机测试授权 | `docs/game-knowledge.md` |
| 维护"收鱼产物"单缸挂机功能 | `docs/features/collect-fish.md` |
| 维护"多鱼缸巡检"循环任务 | `docs/features/patrol.md` |
| 维护"海星喂食"定时机制 | `docs/features/starfish-feeding.md` |
| 维护"鱼食预算"计算逻辑 | `docs/features/fish-food-budget.md` |
| 维护"购买鱼食"独立模块 | `docs/features/buy-fish-food.md` |
| 维护"活动页面/每日签到/特惠礼包"全局处理 | `docs/features/daily-sign.md` |
| 维护"开贝壳"活动自动化 | `docs/features/open-shell.md` |
| 维护"好友摸宝"巡访与采集 | `docs/features/friend-gem.md` |
| 维护"钓鱼达人"导航与活动 | `docs/features/fishing.md` |
| 维护"海獭摸宝"特定宝石寻宝与采集 | `docs/features/sea-otter-gem.md` |
| 维护"乐队鱼演出"邀请与演出活动 | `docs/features/band-fish.md` |
| 维护"浪漫满屋"情侣鱼祝福 | `docs/features/romantic-house.md` |
| 维护"金海豚小游戏"活动自动化 | `docs/features/golden-dolphin.md` |
| 维护"驯鹿鱼送收礼物"日常子任务 | `docs/features/reindeer-fish.md` |
| 维护"日常收尾"每日串联总控任务 | `docs/features/daily-routine.md` |
| 查询游戏通用 UI 识别约定 | `docs/ui-conventions.md` |

## 新 Agent 对话接手顺序（必须执行）

新加入的 Agent 在当前对话或后续对话中接手项目前，按以下顺序建立上下文，不能只看最后一条用户消息就直接改代码：

1. 完整阅读本文件 `AGENTS.md`，先掌握硬规则、工具边界和文档路由；
2. 阅读 `PRODUCT.md`，确认项目定位、架构、禁止事项与非目标；
3. 阅读 `docs/handoff/CURRENT.md`，区分“代码已实现”“代码级验证通过”“MFA 实机通过”和“仍待取证”；
4. 阅读 `docs/handoff/DEVELOPMENT_PLAYBOOK.md`，了解用户偏好、证据模式、AGY 边界和历史事故；
5. 根据文档路由表阅读本次任务对应的 `docs/features/*.md`；涉及资源消耗时再读 `docs/game-knowledge.md`，涉及模板/OCR/通用按钮时再读 `docs/ui-conventions.md`；
6. 执行 `git status --short`，检查当前差异与未跟踪文件；修 bug 时同时定位对应时间段的 MFA/MaaFramework 日志；
7. 最后再阅读目标 Pipeline、Agent 实现和相应 `dev/test_*.py`，建立“需求 -> 当前 UI 状态 -> 节点 -> Action/Reco -> 测试”的完整映射后才能修改。

详细的接手检查表、证据模式和验证矩阵见 `docs/handoff/DEVELOPMENT_PLAYBOOK.md`。实时代码、日志和当前用户纠正的优先级始终高于历史文档；发现冲突时先修正文档，不得沿用已被用户否定的结论。

## 核心文件速查表
| 文件路径 | 模块说明 | 关键注意点 |
| --- | --- | --- |
| `agent/main.py` | Agent 子进程入口 | 参数解析通过 `socket_id=` 前缀匹配。 |
| `agent/my_reco.py` | Python 自定义识别器 | 包含 `CheckDutyCycleReco`, `CheckStarfishTimerReco`, `CheckOpenShellLoopReco`，注意去 emoji。 |
| `agent/my_action.py` | Python 自定义动作 | 包含 `CalcFishingFoodAction`、`FishingCastAndBiteQTEAction`、`SeaOtterHarvestAction` 等。 |
| `agent/runtime_state.py` | 共享运行时状态容器 | 解耦 `my_action.py` 与 `my_reco.py` 的循环引用。 |
| `agent/param_utils.py` | 参数安全解析工具 | 所有 CustomAction/CustomRecognition 统一使用 `parse_dict_param`，防御 `"null"` 字符串。 |
| `agent/requirements-release.txt` | 发布依赖清单 | 新增第三方 import 必须同步更新此文件。 |
| `assets/interface.json` | 任务选项配置 | 修改后需手动同步至 `client_avalonia/` 和 `client/`。 |
| `assets/resource/pipeline/` | 模块化任务流水线目录 | 包含 `common/`、`routine/`、`features/` 业务流水线及 `collect_fish.json` 主干。原 `my_task.json` 保留为 `.bak` 回滚备份。 |
| `assets/resource/pipeline/collect_fish.json` | 任务主干流水线 | `client_avalonia/resource` 通过 junction 链接至此，修改一处即可生效。 |
| `dev/test_pipeline_regex.py` | Pipeline 正则双层校验 | 修改 Pipeline 后**必须**运行，防止 `std::regex` 加载失败。 |
| `dev/test_agent_registration_refs.py` | Pipeline 引用一致性校验 | 静态确保 Pipeline 引用的所有 custom_action/reco 均在 Agent 中注册。 |
| `dev/test_release_agent_imports.py` | 发布包 import 冒烟测试 | 在 embedded Python 环境下验证所有依赖可正常导入。 |
| `dev/test_update_contract.py` | 自动更新契约静态门禁 | 静态校验 interface.json、github 字段、SemVer、资产命名匹配与包排他性。 |

---

## 开发与架构硬规则 (Hard Architectural Rules)

### Bug 修复后的文档闭环规则 (Bug Documentation Closure)

- 用户要求修复的 Bug 在实现完成并通过约定的代码级验证后，交付前必须同步检查 `ISSUES.md`、`docs/handoff/CURRENT.md`、`PROJECT_STATUS.md` 和对应功能文档。
- 已完成的 Bug 必须从“待修复”“进行中”“下一步修复”等待办列表中删除，或迁移为明确的已完成记录；禁止仅更新代码而遗留失效待办。
- 若用户本次只要求代码修复、不要求 MFA/模拟器测试，应标记“代码级验证完成，本次未做实机测试”，但不得因此继续把该 Bug 记作待修复；仍需实机验证的独立业务分支可以作为单独验证事项保留。
- 若 Bug 只完成了一部分，只保留尚未满足的具体子项，不得继续使用已经过期的整条原始待办描述。
- 用户明确说明为本次 Bug 临时复制到项目目录的日志、测试报告或现场截图，只用于本轮取证；任务修复并完成代码级验证后，必须核对准确路径并删除这些临时副本，同时在交付结果中说明已清理。不得据此删除项目长期保留的正式日志或证据资产。

### Bug 修改流程规则 (Direct Bug Fix Workflow)

- 修复 Bug 时不要求先新增或运行“预期失败”的回归测试来复现失败；先直接阅读当前文档、代码和已有现场证据，能够确认根因时立即做最小修改。
- 测试用于修改完成后的代码级验证和防止以后回退；可以按需补充契约断言，但不得把“先制造一次失败测试”作为开始修复的固定步骤。
- 根因仍不明确、且属于用户准备后续实机观察或优化的事项时，保留为待验证/待优化，不为满足测试流程而猜测性修改。

### 步骤可恢复导航架构 (Step-resumable Navigation)
对于存在连续多步 GUI 流程的任务（`Step 1 -> Step 2 -> Step 3 -> ...`）：
- **禁止硬编码单一起点**：任务入口不得假定用户必然处于 `Step 1`，禁止为了满足线性脚本结构强行退回第一步；
- **状态驱动恢复**：每次任务启动或重启时，必须基于当前真实截屏判定用户处于哪个已支持阶段；
- **真实页面原则**：`Current UI State > historical progress`，严禁使用外部变量或上次记录猜测阶段；
- **最深阶段优先（Deepest-First）**：
  ```text
  Task -> StartRouter
            ├─ DeepestKnownStage (如已在终态/场景内)
            ├─ IntermediateKnownStage (如已在中间地图/面板)
            └─ EarliestKnownStage (如还在初始主界面)
  ```
- **契约明确**：任务支持的中途启动阶段必须在任务文档与说明（Start Contract）中明确记录。除业务明确要求或中间状态不可安全识别外，一律提供步骤可恢复兼容。

### 动作前置状态确认规则 (Pre-Action State Verification Rule)
**任何自动化点击前，必须显式验证“当前页面所处真实状态”，严禁臆测或直接穿透点击：**
- **严禁跨层盲点**：绝对禁止在上一阶段（如主鱼缸）未确认转换成功时，直接向下一阶段（如游乐园面板）的固定坐标盲目下发点击；
- **禁止失败跌入固定坐标**：当视觉模板或 OCR 未识别到目标时，坚决杜绝“盲点固定坐标保底”（如金海豚盲点 `(674, 468)` 导致点中鱼缸鱼，或乐队鱼未确认选中好友就盲点邀请按钮）；
- **门禁未达直接熔断**：前置状态未达成或关键模板缺失时，必须记录显式 `ERROR` 日志并安全终止/返回重试，宁可安全停机，绝不引发未预期的破坏性误触。

### 模板资产复核规则 (Template Asset Review Rule)

任何由 AGY、脚本或人工截图生成、将用于 `TemplateMatch` 的模板，在进入正式 Pipeline 前必须由主 Agent 完成以下复核：

1. 同时查看模板图与其来源完整截图，确认目标在真实页面中的上下文；
2. 区分固定 UI 元素与随机/动态内容（游动的鱼、粒子、数字、倒计时、背景动画、活动装饰等）；
3. 模板应紧密裁剪到固定且可复现的目标本体，尽量排除圆框外背景、邻近控件和动态元素；
4. 亲自打开最终 PNG 检查裁剪结果，不能只依据 AGY 的文字说明或坐标报告；
5. 若无法可靠判断某个像素区域是否固定、可复现，立即停止采用该模板并请用户判断，禁止带着不确定性继续接入流程。
6. **点击/识别哪里，就从哪里的真实页面状态截图**：不得因为两个控件肉眼看起来相似，就复用另一页面、另一尺寸或另一状态下裁出的模板。即使图案主体相同，缩放、外框、阴影和抗锯齿差异也会导致 TemplateMatch 失效；主页面图标、展开选择器图标、选中态图标必须分别取证、分别验证。

### Maa Pipeline 正则规则 (Maa OCR Regex Rules)
- **Maa OCR expected 字段按正则表达式解析**：任何出现在 `expected` 字段中的文本均会被 MaaFramework 底层作为 `std::regex` 编译校验。
- **括号与特殊字符约束**：若匹配内容含有正则特殊字符（如 `()`, `[]`, `{}`, `.`, `+`, `*`, `?`, `^`, `$`, `|`），必须在 JSON 中进行双反斜杠转义（如 `\\(`），或优先选取不含特殊字符的稳定中文语义关键词（例如优先匹配"刷新体力"而非"0(0点刷新体力)"）。
- **静态强校验约束**：单个节点的正则语法错误会导致整份 Pipeline 加载校验（`PipelineChecker::check_all_regex`）失败，直接引发客户端"资源加载失败"。修改 pipeline 后务必运行 `python dev/test_pipeline_regex.py` 执行双层校验。
- **真实事故案例**：曾将 `expected: "0("` 写入 Pipeline，Maa 将 `(` 当作 `std::regex` 中未配对括号，编译抛出 `Unmatched marking parenthesis`，导致**整个 Pipeline 资源加载失败**。优先使用语义短语（如"刷新体力"）可彻底规避此类风险。

### Release Runtime Dependency Rule（发布运行时依赖规则）

新增 Agent 第三方依赖是高风险操作，遵守以下规则：

1. **开发机能 import 某库 ≠ 正式发布包包含该库**。嵌入式 Python 环境与开发机完全独立。
2. **Agent 新增任何第三方 `import` 时**，必须同步在 `agent/requirements-release.txt` 中声明该依赖。
3. **Windows x64 发布验证必须使用发行包自带的 embedded `python.exe`** 真实执行导入，仅检查文件存在无效。
4. **验证脚本**: `python dev/test_release_agent_imports.py`，验证 `maa`、`numpy`、`cv2` 及所有 Agent 模块完整导入。
5. **CI 硬门禁**: `verify (win, x86_64)` Job 必须在真实 Windows 上下载 artifact 并执行冒烟脚本，通过后方可发布 Release。
6. **发布阻断规定**：若开发环境依赖存在但 `requirements-release.txt` 未声明，视为发布阻断问题，不允许合并/打 tag。

**背景**：v0.4.2 因发行包 embedded Python 缺少 `opencv-python-headless`，导致 `agent/my_action.py` 顶层 `import cv2` 失败，Agent 进程退出，IPC socket 未建立，MFA 报 `Failed to LinkStart agentClient`。v0.4.3 通过上述机制修复并永久防范。

### Execution Environment Boundary（执行环境边界规则）

Agent 运行在用户当前活跃开发机上，以下约束必须严格遵守：

1. **Agent 只能对当前实际运行机器执行命令**，不能访问用户的其他设备（台式机、测试机等）。
2. **用户提到"另一台电脑"不等于 Agent 获得那台机器的访问权**，绝不自行安排任何跨机器操作。
3. **明确禁止**：
   - "把项目复制到台式机"
   - "去另一台电脑测试"
   - "在台式机解压 artifact"
   - 任何假设自己能在另一台机器执行命令的行为
4. **跨机器验证明确区分**：
   - **Agent-side verification**：当前开发机上可执行的验证（如 CI artifact 下载、本地 import 测试）
   - **User-side verification**：需要用户在另一台设备手动操作（如下载 GitHub Release 到台式机运行测试）
5. **优先原则**：若项目已有 CI artifact 或 GitHub Release，优先让用户直接从 GitHub 下载正式产物到目标设备，而非要求用户手工搬运整个开发目录。

### Scarce-resource Exploration（稀缺资源 GUI 探索规则）

游戏内部分操作每次机会稀缺、不可逆、有资源消耗：

**典型稀缺资源**：
- 每天一次的演出体力（乐队鱼）
- 一枚鱼饵（钓鱼）
- 一次寻宝进入机会（海獭）
- 点击后不可逆的货币/体力消耗

**廉价鱼食测试例外**：当购买和投放目标已经通过视觉门禁明确限定为“廉价鱼食”时，金币购买和鱼食投放不按稀缺资源处理，可以为完成完整流程进行充分、重复的实机测试。详细授权边界见 `docs/game-knowledge.md`；此例外不适用于贝币、钻石、现实付费、其他商品或限次体力。

**开发规范**：
1. 先探索到动作的**前一状态**截图/OCR/ROI，绝不先消耗再观察
2. 尽量使用 replay / mock / dry-run 验证状态机逻辑
3. 真正消耗的操作只在**必要阶段且已充分准备**后执行
4. 一次真实机会必须同时尽量采集：screenshot、OCR 文本、bbox 坐标、页面切换时序、完整日志
5. 绝不为了"验证代码是否跑通"而反复消耗稀缺资源

### Phased Collaboration（分阶段协作规则）

新功能开发若满足以下任意条件，必须采用分阶段协作模式：
- 步骤多，业务机制尚不清楚
- 涉及稀缺资源
- 需要 GPT 审阅状态机设计

**分阶段模式**：
```
Step 1 探索（截图/OCR/路径）
→ 向 GPT/用户汇报
→ GPT 判断状态机/下一步
→ Step 2
→ 汇报
→ Step 3 ...
```

**Agent 自主范围**：每个 Step 内的普通技术问题（OCR ROI 调整、模板裁剪、日志分析、小型 bug、mock 测试）Agent 可以自主处理，不需要频繁打断用户。

**需要 checkpoint 的情况**：
- 进入新的业务阶段
- 即将消耗稀缺资源
- 状态机设计存在重大歧义
- 发现与预期行为显著不符的现象

### CustomAction / CustomRecognition 实现规范

- **必须显式返回 `True` / `False`**（Action）或 `RectType | None`（Recognition），不能靠 Python 默认返回 `None`。
- `custom_action_param` 和 `custom_recognition_param` 可能收到字符串 `"null"`（Pipeline 未配置参数时），必须通过 `agent/param_utils.py` 的 `parse_dict_param()` 安全解析，不能直接 `json.loads()`。
- 所有新增 Action/Reco 均需统一走 `param_utils` 工具函数，防御 null、空字符串、类型错误等边界情况。
- **引用完整性门禁**：修改 Pipeline 或 Agent 后**必须**运行 `python dev/test_agent_registration_refs.py`，保证 Pipeline 中所有引用的 `custom_action` / `custom_recognition` 均在 Agent 中存在对应注册，禁止悬空引用。
- **观测与日志非阻断原则**：观测/日志逻辑不应成为关键业务流的必经 CustomAction，除非该 Action 本身承担必要状态变更。避免因日志动作未注册或回调异常而阻断核心导航。

### GitHub In-App Auto-Update Contract (程序内原生自动更新契约)

MaaHappyFish 采用 MFAAvalonia 原生支持的二合一整包（UI + MaaFW + Agent + Python + Resource）程序内自动更新机制：

1. **配置格式契约**：
   - `interface.json` 中的 `github` 字段必须为纯文本 URL（如 `"github": "https://github.com/zhimaheiye/MaaHappyFish"`），严禁末尾斜杠，严禁写成 markdown 链接格式 `[https://...]`。
   - 三份 `interface.json`（`assets/`、`client/`、`client_avalonia/`）必须保持版本号与内容字节级完全一致。
2. **整包原子覆盖契约（Full Package Update）**：
   - 发行包包含根目录核心应用文件（`MFAAvalonia.exe`、`MaaFramework.dll` 等），触发 MFA 的二合一整包覆盖机制（`ContainsCoreApplicationFiles`）。
   - 第一阶段清理旧 `resource/` 与 `agent/` 并覆盖至数据目录；第二阶段覆盖安装目录中的所有程序与 `python/` 环境文件。
   - 运行中的 `MFAAvalonia.exe` 通过热替换重命名为 `.backupMFA` 并自动重启生效。
3. **用户配置非破坏性契约（Non-Destructive User Config）**：
   - 用户的本地设置（`config/`、`logs/`、`debug/`、设备连接与绑定状态）受保护，更新流程绝不覆盖或擦除。
4. **CI 门禁与发布防线**：
   - 静态校验脚本 `dev/test_update_contract.py` 纳入本地与 CI 硬门禁，发版前必须 100% 通过校验。
   - 资产匹配确保兼容 `\b(?:win|windows)-(?:x64|x86_64)\b` 规则，发布资产命名保持 `MaaHappyFish-win-x86_64-v*.zip`。

### Tool Boundaries & Environment Protection (工具职责边界与环境保护硬规则)

在执行复合型自动化与协同任务时，必须严格区分工具的物理定位与控制边界，**严禁跨界越权操作**：

1. **FastCTX（命令行环境辅助）**：
   - 任务涉及查看代码、执行终端命令、编译、测试、Git 操作或环境检查时，**优先考虑使用 FastCTX**；
   - 避免大量零散命令导致上下文丢失；若连续出现命令失败，必须立即停下重新检查工具选择，严禁盲目重复重试。
2. **maa-mcp（Android 模拟器与游戏客户端专控）**：
   - 唯一职责是操作 Android 模拟器 / 游戏客户端（截图、点击、输入、滑动、OCR、MaaFramework 调试）；
   - **严禁使用 maa-mcp 或 ADB 窥探/控制 Windows 物理窗口、枚举 Windows 应用、操作浏览器或桌面软件**；
   - **ADB 绝不等于 Windows 窗口管理工具**，严禁使用 ADB 查询电脑窗口或查找浏览器。
3. **Kimi 插件（GPT 协作通信通道）**：
   - 用户提供目标浏览器窗口与 GPT 对话链接时，**必须且只能新建 Agent 专用浏览器页面**（`navigate` with `newTab: true`, `group_title: agent:...`）；
   - 必须核验返回的专属标识（`tabId` 与 `agent:` 标签组），确认工作上下文与用户页面物理隔离；
   - **严禁使用 `active: true` 借用用户当前活跃标签**，绝不切换用户正在看的页面，绝不修改用户网页状态；
   - 未检测到 Agent 专属标识时，严禁将当前页面当作工作页面，必须重新建立或向用户汇报。
4. **用户环境保护原则（电脑非纯测试机）**：
   - 任何操作前执行“三确认”：确认操作对象、确认当前窗口、确认当前设备；
   - 发现连续失败、环境不确定或工具异常时，立即触发熔断，停止执行，向 GPT/用户汇报后依规恢复。
