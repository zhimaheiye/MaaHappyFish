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
| 接手当前工作或查看进度 | `docs/handoff/CURRENT.md` |
| 维护"收鱼产物"或"巡检收宝"功能 | `docs/features/collect-fish.md` |
| 维护"海星喂食"定时机制 | `docs/features/starfish-feeding.md` |
| 维护"鱼食预算"计算逻辑 | `docs/features/fish-food-budget.md` |
| 维护"开贝壳"活动自动化 | `docs/features/open-shell.md` |
| 维护"好友摸宝"巡访与采集 | `docs/features/friend-gem.md` |
| 维护"钓鱼达人"导航与活动 | `docs/features/fishing.md` |
| 维护"海獭摸宝"特定宝石寻宝与采集 | `docs/features/sea-otter-gem.md` |

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
| `assets/resource/pipeline/my_task.json` | 启动与活动任务流水线 | 包含 `OpenShellTask`、`SeaOtterGemTask`、`FishingTask` 状态机。 |
| `assets/resource/pipeline/collect_fish.json` | 任务主干流水线 | `client_avalonia/resource` 通过 junction 链接至此，修改一处即可生效。 |
| `dev/test_pipeline_regex.py` | Pipeline 正则双层校验 | 修改 Pipeline 后**必须**运行，防止 `std::regex` 加载失败。 |
| `dev/test_release_agent_imports.py` | 发布包 import 冒烟测试 | 在 embedded Python 环境下验证所有依赖可正常导入。 |

---

## 开发与架构硬规则 (Hard Architectural Rules)

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
