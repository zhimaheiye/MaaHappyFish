# 2026-11-15 摇一摇入场后误停

保留未修改的 MaaFramework 错误原图，供后续背景识别排查；不是新建测试脚本或实机运行报告。

| 文件 | 原始位置 | 修复后同帧识别 |
| --- | --- | --- |
| playing-142929.png | `client_avalonia/debug/on_error/2026.11.15-14.29.29.204_ShakeGameNavigation.png` | 数:10，0.894170；10.4S，0.981647；And 命中 |
| playing-144603.png | `client_avalonia/debug/on_error/2026.11.15-14.46.03.308_ShakeGameNavigation.png` | 数:10，0.894170；10.5S，0.975537；And 命中 |

日志：`client_avalonia/logs/log-20261115.log` 对应时间均为「入场点击后未确认局内或结算，未重复点击」。`client_avalonia/debug/maafw.log` 14:46:00～03 的旧分数 OCR 为「兰」（0.157537）及「数：1」（0.864491），未匹配 `分[数數]`。当前页面是游戏进行中，不能把用户后来拍到的结算画面当成失败瞬间。

使用已安装 MaaDebugger 1.20.1、项目 MaaFramework 5.12.3 和当前真实 Pipeline 做静态截图识别。三张非局内原图 `2026.11.12-22.23.05.378_ShakeGameNavigation.png`、`2026.11.09-11.59.42.891_SeaDiveSubmarineEntry.png`、`2026.11.10-11.39.33.573_PrincessClaimResultRouter.png` 的 And 结果均为 false。首张为海星管理页，属于不同原因，未归入这次分数漏识别。

18项既有测试、321条正则、1004节点原生加载、Agent注册引用通过。未操作模拟器、未做完整任务实测；其它背景仍待自然运行观察。修复契约见 [摇一摇](../../../features/shake-game.md)。
