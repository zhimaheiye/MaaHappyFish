# 客户端图标

发布安装脚本使用项目 `happyfish.ico` 生成安装目录的 `Assets/logo.ico`，供 MFAAvalonia 客户端显示项目图标；开发客户端同步方式见 `tools/sync_dev_client.ps1`。

2026-09-15 已完成项目图标接入，并将图标变更纳入发布工作流触发条件。当次完成代码级验证，未做客户端 UI 测试。

## 两个图标通道

图标有两套来源，改其一不会影响另一个：

- **运行时图标**（托盘、MFA 界面左上角）：读安装目录的 `Assets/logo.ico`，由发布安装脚本从 `happyfish.ico` 生成；
- **资源管理器 / 快捷方式图标**：读 exe 文件内嵌的 PE 图标资源，只换 `logo.ico` 不会改变它们，必须在打包阶段把图标写进 `MaaHappyFish.exe`。

打包阶段的嵌入路径（当前实现，以 HEAD 为准）：

1. `tools/embed_exe_icon.py`：先在 `tools/.icon-patch/`（已 gitignore）内 `npm install resedit`，再调用 node 脚本重写 exe 的 PE 图标资源；
2. `tools/set_exe_icon.mjs`：用 resedit 把 `happyfish.ico` 的全部图标组替换进 exe，使资源管理器与快捷方式显示项目图标；
3. `dev/test_update_contract.py` 断言上述工具存在，且 CI verify job 会检查发行包 `bundle/MaaHappyFish.exe` 确实内嵌了 `happyfish.ico` 的图像 payload，防止打包时漏嵌。

`happyfish.ico` 应包含多尺寸图像（16/32 等），保证资源管理器小图标与托盘显示清晰。
