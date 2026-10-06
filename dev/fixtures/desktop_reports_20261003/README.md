# 台式机报告长期证据

此处保留本轮修复/未决调查所需的 15 份关键文件（含 2 张原图），不是整个临时报告备份。`manifest.json` 保存原来源路径、字节数和 SHA256；清理前再次核对所有源文件和副本，共 2,640,204 字节，全部一致。图片仅作离线现场帧，不作为新运行模板。

用户已授权删除原报告目录。2026-10-03 指定准确路径尝试递归删除，执行工具被策略拒绝（`blocked by policy`），因此原目录仍保留，用户可自行清空；上述留存证据与功能文档不依赖原目录存在。

- `sea_otter/`：夜间末位现场、夜间未用体力弹窗、两次 GUI 和对应终点框架日志。新版报告的 12 点弹窗没有复制为夜间现场。状态机历史依据是 Git tag v0.4.8/v0.4.9/v0.6.0/v0.7.0～v0.7.4，修复及未决项见 `docs/features/sea-otter-gem.md`。
- `patrol/`：幸运时刻挂起到空帧失败与拉起原始日志。缺失的是同时段 MaaFramework 调用/返回、MuMu 事件与实际外部值守器源码；详见 `docs/features/patrol.md`。
- `client_update/`：下载 EOF、ZIP 半包、资源未覆盖、后续安装成功与元数据 TLS 失败、更新后巡检原文。网络断开根因与原生更新器修复仍未完成；详见 `docs/features/client-update.md`。

`dev/test_sea_otter_boundary_recovery.py` 仅用已保存的末位图片和 CustomController 测试真实框架失败状态，绝不连接真实设备。没有进行 MFA、浏览器或模拟器交互测试。
