# MaaHappyFish

开心水族箱挂机小助手。基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework)、[MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia) 与 Python Agent，通过图像识别完成收鱼、定时喂海星和挂机巡检等操作。

## 平台支持

- **正式支持：Windows x64 + MuMu 模拟器 v5+**
- 实验性构建：Windows ARM64、Linux、macOS、Android

维护者目前只在 Windows x64 与 MuMu 模拟器上开发和验证。其他平台由 MaaFramework 与 MFAAvalonia 的跨平台能力生成，但未经维护者测试，不保证可用。

## 功能

- 循环收取鱼产物
- 持续收宝或按周期巡检收宝
- 定时为萌海星补充鱼食
- 根据目标挂机时间计算鱼食预算
- MFAAvalonia 面板内显示运行状态与日志

本项目只使用视觉识别和模拟点击，不读取或修改游戏封包，不提供任何付费、购买或充值操作。

## 当前测试状态与已知问题

- 目前仅“持续监测鱼缸并定期补充鱼食”有相对稳定的运行记录，其他功能尚未完成充分测试。
- 目前观测到的最长无人工干预稳定运行时间约为 **1 小时**，更长时间的稳定性暂不保证。
- 长时间未查看时，任务界面可能仍显示运行中，但游戏已经退出至模拟器桌面。该问题尚未修复，请勿依赖本项目进行长时间无人值守运行。

最新说明同时记录在 [RELEASE_NOTES.md](./RELEASE_NOTES.md)，并会自动附加到 GitHub Release 正文。

## 下载与使用

1. 从 [Releases](https://github.com/zhimaheiye/MaaHappyFish/releases) 下载名称包含 `MaaHappyFish-win-x86_64` 的压缩包。
2. 完整解压到一个独立目录，不要直接在压缩包内运行。
3. 启动 MuMu 模拟器与游戏；默认 ADB 地址为 `127.0.0.1:16416`。
4. 运行 `MFAAvalonia.exe`，选择安卓控制器与对应设备后执行任务。

Windows x64 正式发行包自带 Python 与 `maafw`，用户不需要另外安装 Python、MaaFramework 或 MFAAvalonia。

当前资源以 OPPO 服界面为基准。游戏更新、分辨率变化或网络波动可能造成识别失败，请先停止任务并保留日志后再反馈。

## 故障日志收集

Windows 发行包根目录自带 `collect-test-report.cmd`。出现问题后：

1. 记录问题发生的大致时间，停止任务并关闭 MFAAvalonia。
2. 双击 `collect-test-report.cmd`。
3. 在桌面的 `MaaHappyFish-TestReports` 文件夹中找到生成的 ZIP。
4. 将 ZIP 与问题时间、运行时长和相关截图一起交给维护者分析。

收集器只打包最近 3 份 `logs/*.log` 和测试信息，不收集账号配置、不包含截图，也不会自动上传任何内容。

## 开发

源码目录与本地运行目录相互分离：

- `agent/`：Python Agent 与自定义识别、动作
- `assets/`：Project Interface、Pipeline 和图片资源
- `tools/`：资源校验与发行包组装脚本
- `client_avalonia/`：本地调试运行目录，不提交到 Git

本地开发需要 Python、`maafw` 与 Node.js。常用代码级检查：

```powershell
npm ci
npx @nekosu/maa-tools check
python tools/validate_schema.py --schema-dir deps/tools --resource-dirs assets/resource/pipeline --interface-files assets/interface.json
python -m compileall agent tools
```

## 发布

GitHub Actions 会在推送 `v*` 标签后自动组装并发布各平台产物。Windows x64 包会额外内置嵌入式 Python 和 `maafw`。

```powershell
git tag v0.1.0
git push origin v0.1.0
```

版本号会在打包时自动写入 `interface.json`，无需手工修改。

## 免责声明

本项目与《开心水族箱》及其运营方无隶属或合作关系，仅供学习和个人自动化测试使用。使用自动化工具可能违反游戏服务条款或导致账号风险，使用者应自行判断并承担后果。

## 许可证

MaaHappyFish 自有源码使用 [MIT License](./LICENSE)。发行包包含按各自许可证分发的第三方组件，详见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。
