# 当前交接档案 (CURRENT.md)

**更新时间**: 2026-08-29 00:55

## 当前状态概要
核心功能群全部生产就绪，UI 日志播报机制已完整验证（focus 注入 + 节流）。

## 已完成事项 (Completed)
- [x] 收鱼产物主干循环逻辑 (`ResumeHarvest` 万能节点中转模式)
- [x] 海星定时自动喂食 (基于 `wall-clock` 解耦 Pipeline `timeout`)
- [x] 防误触等待逻辑 (`4.5s` 自然消退替代乱点水域)
- [x] 巡检收宝（占空比休眠/激活状态机切换）
- [x] 挂机鱼食预算自动计算与 UI 界面播报 (`CalcFishingFoodReco` Custom Recognition 原生 focus 注入)
- [x] 清除所有 Emoji，修复 GBK 崩溃
- [x] 修复 `main.py` socket_id 参数解析 (`socket_id=` 前缀匹配)
- [x] MFA UI 日志面板动态播报（`focus` 字段 + `context.override_pipeline` 注入）
- [x] UI 播报去重：统一单事件 key 挂载，消除多条重复打印
- [x] 启动首秒模式概览播报：持续实时模式与休眠定时模式均在启动时明确播报当前状态
- [x] UI 播报节流：休眠期间每 60 秒最多一条状态消息，状态切换事件仍即时播报
- [x] 修复海星喂食 on_error 死循环导致的狂点左上角退出软件 Bug（安全熔断 + 自愈守护）
- [x] 海星喂食动作全链路延时与稳定性加固（给足 1.8s 弹窗展开 + 2.0s 充能动画 + 2.0s 平稳退出）
- [x] 海星喂食进度条视觉回执校验（`CheckFoodFull` 匹配 `鱼食已装满.png`，成功/不足明确回执播报）
- [x] 修复海星误点蓝色加号打开购买商店的问题，改为点击普通鱼食袋并安全回执
- [x] 消除校验候选与返回候选并列导致的提前退出；满仓校验限定到进度条右端 ROI
- [x] 修复 `CalcFishingFoodAction` 的 `extra_mins` 未定义分支
- [x] 完成 MaaHappyFish 首发整理：公开 README、项目命名、许可证声明与 GitHub Release 工作流
- [x] Windows x64 发行包内置 Python 3.13 与 MaaFw；其他平台保留为未经维护者验证的实验性构建

## 待验证事项 (To Verify)
- [ ] 连续挂机稳定性测试（验证杜绝狂点左上角后不再退回桌面）
- [ ] 在萌海星存粮不满时做一次端到端喂食验证，确认鱼食数量减少且进度条补满

## 暂不实现区域 (Non-Goals)
- 鱼苗养殖相关自动化（范围外）。
- 宝石兑换逻辑（范围外）。
- 任何形式的涉及氪金/付费点击（严禁）。

## 交接备忘 (Handoff Notes)
- `interface.json` 改动后，**务必**手动分发覆盖 `assets/`、`client_avalonia/` 和 `client/`，junction link 仅覆盖了 `resource` 文件夹。
- 调试遇到 Agent 无故终止时，第一时间检查是否有新引入的代码打印了 UTF-8 特殊字符（如 Emoji）。
- MFA UI 日志面板的内容来源是 Pipeline `focus` 字段触发的框架回调，**不是** Python `print()`。如需在 UI 显示动态消息，应在 Python Agent 中调用 `context.override_pipeline()` 注入目标节点的 `focus` 内容。
