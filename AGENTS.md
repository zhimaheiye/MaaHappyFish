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
| 维护“收鱼产物”或“巡检收宝”功能 | `docs/features/collect-fish.md` |
| 维护“海星喂食”定时机制 | `docs/features/starfish-feeding.md` |
| 维护“鱼食预算”计算逻辑 | `docs/features/fish-food-budget.md` |
| 维护“开贝壳”活动自动化 | `docs/features/open-shell.md` |
| 维护“好友摸宝”巡访与采集 | `docs/features/friend-gem.md` |
| 维护“钓鱼达人”导航与活动 | `docs/features/fishing.md` |
| 维护“海獭摸宝”特定宝石寻宝与采集 | `docs/features/sea-otter-gem.md` |

## 核心文件速查表
| 文件路径 | 模块说明 | 关键注意点 |
| --- | --- | --- |
| `agent/main.py` | Agent 子进程入口 | 参数解析通过 `socket_id=` 前缀匹配。 |
| `agent/my_reco.py` | Python 自定义识别器 | 包含 `CheckDutyCycleReco`, `CheckStarfishTimerReco`, `CheckOpenShellLoopReco`，注意去 emoji。 |
| `agent/my_action.py` | Python 自定义动作 | 包含 `CalcFishingFoodAction` 计算器。 |
| `assets/interface.json` | 任务选项配置 | 修改后需手动同步至 `client_avalonia/` 和 `client/`。 |
| `assets/resource/pipeline/my_task.json` | 启动与活动任务流水线 | 包含 `OpenShellTask` 状态机。开贝壳任务需在大章鱼主界面启动。 |
| `assets/resource/pipeline/collect_fish.json` | 任务主干流水线 | `client_avalonia/resource` 通过 junction 链接至此，修改一处即可生效。 |

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
- **括号与特殊字符约束**：若匹配内容含有正则特殊字符（如 `()`, `[]`, `{}`, `.`, `+`, `*`, `?`, `^`, `$`, `|`），必须在 JSON 中进行双反斜杠转义（如 `\\(`），或优先选取不含特殊字符的稳定中文语义关键词（例如优先匹配“刷新体力”而非“0(0点刷新体力)”）。
- **静态强校验约束**：单个节点的正则语法错误会导致整份 Pipeline 加载校验（`PipelineChecker::check_all_regex`）失败，直接引发客户端“资源加载失败”。修改 pipeline 后务必运行 `python dev/test_pipeline_regex.py` 执行双层校验。
