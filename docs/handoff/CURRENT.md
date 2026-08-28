# 当前交接档案 (CURRENT.md)

**更新时间**: 2026-08-28 19:18

## 当前状态概要
核心功能群全部生产就绪，UI 日志播报机制已完整验证（focus 注入 + 节流）。

## 已完成事项 (Completed)
- [x] 收鱼产物主干循环逻辑 (`ResumeHarvest` 万能节点中转模式)
- [x] 海星定时自动喂食 (基于 `wall-clock` 解耦 Pipeline `timeout`)
- [x] 防误触等待逻辑 (`4.5s` 自然消退替代乱点水域)
- [x] 巡检收宝（占空比休眠/激活状态机切换）
- [x] 挂机鱼食预算自动计算与 UI 界面播报 (`LogFoodBudget` focus 注入)
- [x] 清除所有 Emoji，修复 GBK 崩溃
- [x] 修复 `main.py` socket_id 参数解析 (`socket_id=` 前缀匹配)
- [x] MFA UI 日志面板动态播报（`focus` 字段 + `context.override_pipeline` 注入）
- [x] UI 播报节流：每 60 秒最多一条状态消息，状态切换事件仍即时播报
- [x] 修复海星喂食 on_error 死循环导致的狂点左上角退出软件 Bug（安全熔断 + 自愈守护）

## 待验证事项 (To Verify)
- [ ] 连续挂机稳定性测试（验证杜绝狂点左上角后不再退回桌面）

## 暂不实现区域 (Non-Goals)
- 鱼苗养殖相关自动化（范围外）。
- 宝石兑换逻辑（范围外）。
- 任何形式的涉及氪金/付费点击（严禁）。

## 交接备忘 (Handoff Notes)
- `interface.json` 改动后，**务必**手动分发覆盖 `assets/`、`client_avalonia/` 和 `client/`，junction link 仅覆盖了 `resource` 文件夹。
- 调试遇到 Agent 无故终止时，第一时间检查是否有新引入的代码打印了 UTF-8 特殊字符（如 Emoji）。
- MFA UI 日志面板的内容来源是 Pipeline `focus` 字段触发的框架回调，**不是** Python `print()`。如需在 UI 显示动态消息，应在 Python Agent 中调用 `context.override_pipeline()` 注入目标节点的 `focus` 内容。
