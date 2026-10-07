# 待修复问题记录 (ISSUES.md)

本文档只保留尚未完成的问题和明确登记的优化待办，不设已完成记录区。已完成事项的证据、修复说明和验证边界存入对应功能文档；没有文档时新建。项目现状和交接摘要分别维护在 `PROJECT_STATUS.md` 与 `docs/handoff/CURRENT.md`。

## 当前待修复

- 2026-10-03 海獭全部寻宝体力耗尽的判据与继续搜寻路径仍缺证据：已修复末位 RIGHT 被强制改为 LEFT（跳过原 LEFT）、边界假成功/错误计数，以及导航/安全上限误报绿勾。仍不能由末位好友体力 0 推断全部寻宝体力耗尽，当前这些边界明确 FAILED、不新增完整次数。需同次完整切换轨迹、边界好友列表/账号侧余额与已耗尽终态对照，才能决定回扫、好友内换缸或重新搜索；不盲点退出消耗搜索次数。版本对照、事实/推断与待取证点见 `docs/features/sea-otter-gem.md`，关键原始证据在 `dev/fixtures/desktop_reports_20261003/sea_otter/`。

- 2026-10-02 台式机巡检底层长时间静默仍待取证：02:56:05.843→08:00:26 无业务日志而持续内存心跳，最后 `EmulatorExtras` 返回空帧。缺少同时段 MaaFramework 调用/返回日志及 MuMu 系统事件，无法确认采集通道/原生线程阻塞的根因；仅保留此子项，幸运时刻的专属关闭分支已完成，不再列作待修复。原始关键日志已迁到 `dev/fixtures/desktop_reports_20261003/patrol/`，说明见 `docs/features/patrol.md`，不依赖即将清空的临时目录。
- 2026-10-02 外部值守器 `mfa_night_watch.py` 的停滞判据待核对/修复：内存心跳曾导致误报 HEALTHY；新增报告称规则优先级已于 11:40 在外部脚本修复，但仓库没有该源码，无法复核。待拿到实际脚本后核对业务进展判据及去重，不把所有通用失败标记已知；摘要见 `docs/features/patrol.md`，不假造外部实现。

- MFAAvalonia v2.16.2 原生资源更新容错仍待上游或自有客户端修复（2026-10-02 台式机现场，2026-10-03 复核）：历史现场曾出现下载响应体 TLS EOF，留下 131072000 字节且无 ZIP 中央目录/EOCD 的临时半包；另一次先成功校验并安装 v0.7.4，重启后才发生新的 GitHub Release 元数据 TLS 握手失败，后续巡检正常。网络/代理/服务端哪一环导致 EOF 仍无证据。MFAAvalonia v2.16.2 与 2026-10-03 上游当前 `VersionChecker.cs` 均仍存在“内部下载异常返回 false 使外层 WebException 重试难以生效、下载前停止任务、失败 return 后队列仍记录任务完成”等语义；MaaHappyFish 当前发行流程使用官方预编译 MFAAvalonia，不编译这段 C#，因此 Python Agent/Pipeline 不能直接修复。详见 `docs/features/client-update.md`。关键日志在 `dev/fixtures/desktop_reports_20261003/client_update/`。

- MFAAvalonia 原生临时目录清理偶发 `AccessDenied` 待上游或自有客户端修复（2026-10-06 台式机 v0.7.8）：初始化 MaaTasker 时删除 `cache/.temp/.../00000208.bak` 失败，堆栈位于 `MFAAvalonia.Extensions.MaaFW.MaaProcessor.InitializeMaaTasker`；同批日志随后 Agent 正常启动并继续执行任务，当前证据表明它是非阻断告警，不能当作自动化业务失败。MaaHappyFish 使用官方预编译 MFAAvalonia，仓库内 Python/Pipeline 无法修复该 C# 文件占用/权限竞态。复现与边界见 `docs/features/client-update.md`。
