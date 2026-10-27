# 待修复问题记录 (ISSUES.md)

本文档只保留尚未完成的问题和明确登记的优化待办，不设已完成记录区。已完成事项的证据、修复说明和验证边界存入对应功能文档；没有文档时新建。项目现状和交接摘要分别维护在 `PROJECT_STATUS.md` 与 `docs/handoff/CURRENT.md`。

## 当前待修复


- 2026-10-15 15:36:54 MFAAvalonia 以 BEX64 退出，故障模块 `ucrtbase.dll`，异常码 `0xc0000409`。GUI 最后一条业务日志是 15:32:53 巡检正常完成，两路框架日志在崩溃同一秒停止。同日 19:24 海獭按设计在推荐玩家边界安全 FAILED，且未增加今日次数；约 19:24:24 起 GUI 与内存心跳停止，19:51:13 记录 Application Hang（事件 1002，pid 10252）。该时段没有 System 事件 2004，不能写成内存耗尽；19:53:46 人工重启后进程恢复。这两次都属于预编译客户端／原生运行时，本仓库不新增 Pipeline 绕过。见 `docs/features/patrol.md`、`docs/features/sea-otter-gem.md`。

- 2026-10-12 11:36 好友摸宝序号 226 的“下一位”箭头持续约 22 秒未识别，宿主巡检失败。该瞬间没有游戏截图，不能断定列表终点、被其它页面遮挡还是模板瞬时失效。2026-10-20 12:15:38 在连续 12 次没有气泡后又未识别到箭头；当日框架备份只到 11:35，仍没有这帧截图、OCR 或模板最高分。现有代码已改为明确 ERROR／FAILED，不把未知页当成已完成，也不新增固定返回坐标；待同次截图后再决定是否存在可安全收尾路径。见 `docs/features/friend-gem.md`。

- 2026-10-12 18:41 Agent 子进程意外退出，18:42 巡检 Custom 失败出口跨进程调用只有 Starting 无结束；19:39 重新点“开始任务”后截屏亦卡住。现有证据同时有 MuMu `get_display_id` 长时间自旋，但没有 Agent 退出码、崩溃转储或 MuMu 服务侧日志，不能归因到 Python Action。MFAAvalonia／MaaFramework 属预编译组件，本仓库不能修进程重建或 Custom RPC 超时；需上游/自有客户端及同次系统日志取证，不能用 `StopTask` 伪装业务失败。见 `docs/features/patrol.md`。

- 2026-10-11 海獭摸宝“从主鱼缸自动进入并选择目标宝石”的入口模式尚未实现：现有 MFA 任务只在用户手动选好宝石、进入好友列表／好友鱼缸后接管摸宝，运行模式选项只控制收尾返回或停留。`happyfishagent` 当前最新仓库有蓝明镜石的人工导航文字和兑换页／鱼卡气泡截图，但文档所指的完整 19 帧＋57 模板及蓝明镜石专属可复用素材未在检出文件中找到。待取得连续画面／原始素材后，在同一任务内提供明确的手动入口与自动入口、自动入口目标宝石选择；未取证前不以旧坐标点击「确认寻宝」消耗体力。见 `docs/features/sea-otter-gem.md`。


- 2026-10-08 乐队鱼在网络断线弹窗下的演出状态与安全恢复仍缺证据：22:17「请确认网络连接正常哦~()」遮挡「我的演出」，结算等待失败，不能确认此前是否扣除当日唯一演出体力或是否已有未领取结算。当前真实 FAILED、不自动重试消耗体力；待同次网络恢复后的体力、返场／结算和日志对照，再决定是否允许关闭提示并恢复。见 `docs/features/band-fish.md`。

- 2026-10-02 台式机巡检底层长时间静默仍待取证：02:56:05.843→08:00:26 无业务日志而持续内存心跳，最后 `EmulatorExtras` 返回空帧。缺少同时段 MaaFramework 调用/返回日志及 MuMu 系统事件，无法确认采集通道/原生线程阻塞的根因；仅保留此子项，幸运时刻的专属关闭分支已完成，不再列作待修复。原始关键日志已迁到 `dev/fixtures/desktop_reports_20261003/patrol/`，说明见 `docs/features/patrol.md`，不依赖即将清空的临时目录。
- 2026-10-02 外部值守器 `mfa_night_watch.py` 的停滞判据待核对/修复：10 月 12 日 Agent 退出后 `[内存管理]` 心跳、`get_display_id` 自旋仍让值守判 HEALTHY；23:31 失败跨零点后，值守只看当日日志漏掉前一日故障。10 月 13 日两次宝石融合 `[巡检-宝石融合]` 仅有 Monitor 副本且 `StopTask` 假成功，原标签正则 `\[巡检\]` 未覆盖子标签，再次被判 HEALTHY；11:46 和 14:24 更新／重建 Agent 时的“Agent 进程已退出”也被误报为静默挂死。10 月 14 日两次 `MuMuManager.exe` 初始化码 `0xc0000142` 时游戏、MFA 和 ADB 仍活着，值守却归为全面 `ENV_DOWN`；10 月 15 日包中的 `ENV_DOWN` 也有只是读取到队列 FAILED 而非设备失联的例子。旧报告还显示泛化 `任务失败：多鱼缸巡检` 会误归幸运弹窗。2026-10-17 23:53:58 巡检摇晃时 MuMuManager 调用超时 5 秒，当次 shake 失败后继续，巡检完成；2026-10-18 01:19:49 钓鱼 30 秒未咬钩后续钓并完成 5 杆。这两行也被标成新异常，业务没有停。双仓均无实际 `mfa_night_watch.py`，无法在本机修它。待取得脚本后按业务进展与跨日窗口判停滞，区分组件初始化失败／队列失败与全环境失联，覆盖子标签和 Monitor 日志、排除更新窗口，并让具体签名先于泛化兜底。见 `docs/features/patrol.md`。

- MFAAvalonia v2.16.2 原生资源更新容错仍待上游或自有客户端修复（2026-10-02 台式机现场，2026-10-03 复核）：历史现场曾出现下载响应体 TLS EOF，留下 131072000 字节且无 ZIP 中央目录/EOCD 的临时半包；另一次先成功校验并安装 v0.7.4，重启后才发生新的 GitHub Release 元数据 TLS 握手失败，后续巡检正常。网络/代理/服务端哪一环导致 EOF 仍无证据。MFAAvalonia v2.16.2 与 2026-10-03 上游当前 `VersionChecker.cs` 均仍存在“内部下载异常返回 false 使外层 WebException 重试难以生效、下载前停止任务、失败 return 后队列仍记录任务完成”等语义；MaaHappyFish 当前发行流程使用官方预编译 MFAAvalonia，不编译这段 C#，因此 Python Agent/Pipeline 不能直接修复。详见 `docs/features/client-update.md`。关键日志在 `dev/fixtures/desktop_reports_20261003/client_update/`。

- MFAAvalonia 原生临时目录清理偶发 `AccessDenied` 待上游或自有客户端修复（2026-10-06 台式机 v0.7.8）：初始化 MaaTasker 时删除 `cache/.temp/.../00000208.bak` 失败，堆栈位于 `MFAAvalonia.Extensions.MaaFW.MaaProcessor.InitializeMaaTasker`；同批日志随后 Agent 正常启动并继续执行任务，当前证据表明它是非阻断告警，不能当作自动化业务失败。MaaHappyFish 使用官方预编译 MFAAvalonia，仓库内 Python/Pipeline 无法修复该 C# 文件占用/权限竞态。复现与边界见 `docs/features/client-update.md`。
