# 巡检误触活动页的离线负例

来自用户临时报告 `台式机报错调查报告（待修复）/巡检误触活动页_20261002` 的完整 1280×720 PNG 原样副本，仅用于代码级回归，未裁剪或生成新模板。

| fixture | 原始现场 |
| --- | --- |
| `moon_home.png` | 09 月 28 日 12:19:38，误入酿月食香 |
| `sewing_home.png` | 09 月 28 日 16:16:23，误入巧手裁缝铺 |
| `herb_home.png` | 09 月 29 日 20:26:48，误入百草灵仙赐福降世 |
| `moon_reward.png` | 09 月 30 日 11:22:53，酿月食香奖励遮罩 |
| `harvest_board.png` | 10 月 2 日 12:30:58，丰收时节棋盘 |

`dev/test_patrol_activity_mistouch.py` 使用真实 MaaFramework + 只读文件帧的 CustomController 验证门禁；点击和滑动只记录，不连接任何设备。活动画面必须拒绝金币点击及后续扫底，即使金币子识别被强制命中。正例使用已有 `../image/main/tank2_main.png`。
