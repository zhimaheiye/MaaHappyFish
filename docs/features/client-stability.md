# 客户端退出与本机内存调查

## 2026-10-31 结论与处理边界

本次检查 10 月 25 至 31 日 GUI／框架日志、4 个 `MFA_errors_20261027/28/30/31` 证据包、Windows Application 1000／1026 与 System 2004，以及本机现存的 3 份 MFAAvalonia minidump。错误摘录窗口有重复，不能把 manifest 的 hits 相加当作独立事故次数。主仓库先快进到 `89e3a54`；证据仓库当时已与远端 `5ae5046` 一致，未覆盖任何既有改动。

### 原生退出和内存压力

Windows 记录的 MFAAvalonia 原生退出：10 月 27 日 20:44、28 日 08:03／15:44、29 日 18:59、30 日 19:16／23:31、31 日 01:12。28 日 15:44 同 PID 有两条 Application Error，不按两次独立进程崩溃计数。此前“10 月 15 日缺少资源耗尽事件”的历史结论不能套用到本批：本批多次崩溃前后明确存在 System 2004。

| 时点 | System 2004 中的私有提交内存 | 同期退出 |
| --- | --- | --- |
| 10-27 20:44:11 | MuMu 实例 0 约 21.0 GiB，MFA 约 6.7 GiB | 20:44:33 `ucrtbase.dll`／`c0000409` |
| 10-29 18:57:40 | MuMu 实例 0 约 24.7 GiB，MFA 约 11.4 GiB | 18:59:33 `ucrtbase.dll`／`c0000409` |
| 10-30 19:16:23 | MuMu 实例 0 约 29.0 GiB，MFA 约 2.3 GiB | 同秒 `ucrtbase.dll`／`c0000409` |
| 10-30 23:29:44 | MuMu 实例 0 约 30.1 GiB，MFA 约 4.2 GiB | 23:31:03 `VCRUNTIME140.dll`／`c0000005` |
| 10-31 01:12:11 | MuMu 实例 0 约 30.1 GiB，MFA 约 4.1 GiB | 下一秒 `ucrtbase.dll`／`c0000409` |

只读解析 minidump ExceptionStream 和模块表：`MFAAvalonia.exe.77404.dmp`、`.80892.dmp` 均为 `c0000409`，异常参数 `(7,)`，位于 `ucrtbase.dll+0x7286e`；`.11328.dmp` 为 `c0000005`，参数 `(1,32)`，位于 `VCRUNTIME140.dll+0x1de23`，即写入地址 `0x20`。没有符号化调用栈，不能把它写成已确认某个 Python Action／C# 对象泄漏，也不能仅凭 `c0000409` 宣称栈缓冲区溢出。Microsoft 对 [fast-fail](https://learn.microsoft.com/en-us/cpp/intrinsics/fastfail) 与 [Event 2004](https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-application-service-memory-leaks) 的说明用于解释异常和提交耗尽；具体业务归因仍以本机证据为准。

用户本次明确授权只重启 MuMu 实例 0。执行前核对 `MuMuManager info -v 0`：PID 14412、端口 16384；实例 1 为 PID 24904、端口 16416。通过 `control -v 0 restart` 完成重启并确认 Android `start_finished`，新 PID 26304；私有提交从约 34.5 GiB 降至 3.6 GiB，释放约 31 GiB。实例 1 的 PID 与运行状态不变。随后机器约有 16 GiB 可用物理内存、约 34 GiB 可用提交空间；这是一次即时缓解，不是 MuMu 或 MFA 原生内存增长的永久修复。没有执行游戏任务、修改系统分页文件或更换运行库 DLL。

### 开发 Agent 依赖串用

正在运行的开发 MFA 曾启动 `C:\Python313\python.exe`，其 `maafw` 为 5.10.2，而项目 `.venv` 与开发客户端原生库为 5.12.3。这是已证实的开发环境问题，不能据此独自解释宿主原生崩溃。`agent/main.py` 现于第三方导入前调用 `dev_environment.configure_development_imports`：只有真实源码仓库、`assets/interface.json` 和 `.venv/pyvenv.cfg` 同时存在且 Python 主次版本一致时，优先加载项目专用 site-packages。保留同一个 Agent 进程，不重新拉起子 Agent；正式包没有源码仓库标记，继续使用自己的 embedded 环境。系统 Python 安装与其它项目均不变。入口增加实际解释器、Maa 包版本与开发依赖目录日志；这些日志不替代客户端握手证据。

### 普通任务错误的分类

- 10-29 10:25：充值页已打开，批量 OCR 缓存把页头当成大框／无效字符，`DailyFreeGiftRechargePage` 未确认；改为页签紧 ROI 的 `only_rec`，真实页与海星页负例原生回放通过。
- 10-31 01:00：乐队鱼退出后实际落在海星页，却已经推进免费礼包。旧乐队鱼无门禁追加 `(640,150)` 点击，并提前推进队列；现在只在确认演出页／游乐园网格后执行对应退出，连续两帧主缸确认后才沉淀状态。不能证明每次误入海星都由同一条游鱼触发，但已移除明确的不安全点击。
- 10-30 13:18：鱼宝错误截图已经是主页，旧入口路由却提前选择旧主缸重试分支；现在先等待主页最多 8 秒，超时重新识别，仍需已知主缸才重试。后项巡检停在鱼宝页是前项错误的连带结果，不增加跨任务盲退。
- 10-31 00:44：绿野入口在真实主缸图中不可见，不能猜测新入口或判定活动结束；新增消费前入口检查，未确认时在开贝壳和买鱼前真实失败，既有禁止重复消费循环的出口保留。
- 10-31 驯鹿 `AfterCollectRouter` 的 on_error 图对应无回礼正常出口，01:07:28 已成功回缸并推进，01:11:09 整段日常 SUCCEEDED；原生保存 on_error 图片不等于任务失败。巡检误入海星后的恢复截图同理，按后续状态判断。
- 10-30 12:45 启动错误图是「嘎嘎队立大功」活动页，属于未收录活动；不使用其它页面的关闭模板或固定坐标。10-29 10:49 `ShakeGameDone` 错误图是浪漫满屋，页面突变来源尚未确认，仍保留待取证。
- 10-28 20:40 `Value cannot be null (opt)` 的截图执行器重建循环、连接模拟器失败均位于预编译客户端／控制器边界，不靠 Pipeline 猜测修复；此前 Agent 退出通知处于任务重建窗口，无 Python traceback，不能误写为已确认 Python 崩溃。

## 验证与留存

82 项相关 pytest、日常全套 11 组、日常调度、绿野、全局弹窗、发布依赖导入与 Pipeline／注册门禁代码级通过；原生回放仅使用磁盘帧与 CustomController，零游戏输入。未做 MFA 自然业务验收。开发客户端需完整退出重开才能加载 Agent 改动；本次只获准重启模拟器实例 0，没有重启或停止 MFA。

长期回归帧、原始路径及 SHA256 见 `dev/fixtures/stability_20261031/README.md`。原始运行日志、Windows 事件、3 份原生转储保留在本机；不把转储或全日原始日志推入 Git。删除被自动审批拒绝后，改用可恢复归档：仅将已分析的 4 个 `MFA_errors_*.zip` 和本次 `_extract_20261031_logrepair` 移出证据目录，保存在本机忽略目录 `D:/happyfishgame/temp/processed-evidence-20261031/`，未销毁内容；证据仓库所有旧值守 ZIP、用户修改与未跟踪素材保留。已修的普通任务／依赖问题不继续留在 `ISSUES.md`；原生内存增长、未知活动与未知页面突变仍按具体边界登记。

本轮已分析证据包（仅下列四份属于清理范围）：

| 文件 | SHA256 |
| --- | --- |
| `MFA_errors_20261027_040149_5b56bfccf6ac.zip` | `8b6a856c3d97811c1d01342dd45fca4c21632074642a09ef06557ea4622abdb7` |
| `MFA_errors_20261028_040047_4d40761dca84.zip` | `d49c69082e28ef847a5ac9fd4d2733c87ee1467d0f915842b953fa4a1756b9e3` |
| `MFA_errors_20261030_040131_8d232b8dc6d8.zip` | `b1129cb87489adfd0ed3dfc1addb2aec98a8a2c51bbbcd3e90565a6083461094` |
| `MFA_errors_20261031_040222_1ff9cf827398.zip` | `15b6308d3d29496d9084935ab742b6b7835a3553000682cd2aa7c793d86db506` |
