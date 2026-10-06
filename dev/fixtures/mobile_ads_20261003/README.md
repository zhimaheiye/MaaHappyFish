# 手机广告 2026-10-03 原始取证

- `2026.10.03-*.png`：原样复制 `client_avalonia/debug/on_error/` 当日 7 张错误帧；20:19 的续播超时已恢复，其余六张为最终失败。原 MFA 日志和错误截图保留。
- `source_failures.log`：两份对应原日志中当日任务开始、超时和最终失败的原文摘录；`sources.json` 记录原路径与提取时 SHA256。
- `playing_capsule_live.png`：真机 21:04:59，左上仍为“看20s/安装应用立即获得奖励”，右上小叉存在但不能关闭。
- `rewarded_capsule_live.png`：同条广告 21:05:31 已获得奖励，胶囊白叉模板的完整来源。
- `reward_popup_live.png`：胶囊白叉关闭后回转盘并停止，21:07:06 游戏奖励弹窗。
- `download_endcard_live.png`：追加取证 5 轮的第 4 条自动切到白色抖音下载浮层；对应用户 MFA 截图。下载浮层白叉模板的完整来源。
- 完整生产 Pipeline 运行记录见 `temp/mobile_ads_live_20261003/`。`batch_3` 是最初胶囊修复后的 3 轮成功；`batch_5` 是用于发现下载浮层的失败批次，不能作为 5 轮通过；`postfix_5` 是浮层修复后的同页恢复及续跑，首轮来自已有结束页。

最终 `postfix_5` 为 5/5 成功，首轮现场恢复＋4 条完整新广告；`postfix_5_summary.json`、`postfix_5_actions.json` 和 `postfix_5_final.png` 保存可核对的成功结果与大厅画面。

固定帧回归：`python -m dev.test_mobile_ad_rewarded_capsule`，不连接设备。本机临时真机 runner 按项目 `dev/run_*.py` 约定不进入版本控制；显式授权后可执行 `python dev/run_mobile_ad_pipeline_live.py --cycles 3 --out temp/mobile_ads_new_run`。固定 USB 设备 `e5bbf9bd`，使用 Encode 截图与无模拟器 Extras 的输入，设硬截止并确认停止。
