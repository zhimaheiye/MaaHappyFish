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

## 核心文件速查表
| 文件路径 | 模块说明 | 关键注意点 |
| --- | --- | --- |
| `agent/main.py` | Agent 子进程入口 | 参数解析通过 `socket_id=` 前缀匹配。 |
| `agent/my_reco.py` | Python 自定义识别器 | 包含 `CheckDutyCycleReco` 和 `CheckStarfishTimerReco` 状态机，注意去 emoji。 |
| `agent/my_action.py` | Python 自定义动作 | 包含 `CalcFishingFoodAction` 计算器。 |
| `assets/interface.json` | 任务选项配置 | 修改后需手动同步至 `client_avalonia/` 和 `client/`。 |
| `assets/resource/pipeline/collect_fish.json` | 任务主干流水线 | `client_avalonia/resource` 通过 junction 链接至此，修改一处即可生效。 |
