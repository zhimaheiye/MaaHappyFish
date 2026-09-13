# MaaHappyFish

开心水族箱挂机小助手。基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework)、[MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia) 与 Python Agent，通过图像识别完成收鱼、定时喂海星、多鱼缸巡检与日常自动化操作。

## 平台支持

- **正式支持：Windows x64 + MuMu 模拟器 v5+**
- 实验性构建：Windows ARM64、Linux、macOS、Android

维护者目前只在 Windows x64 与 MuMu 模拟器上开发和验证。其他平台由 MaaFramework 与 MFAAvalonia 的跨平台能力生成，但未经维护者测试，不保证可用。

## 功能特性

### 1. 核心挂机与巡检
- **收鱼产物**：当前鱼缸循环收宝，支持空中双倍产物滑动拾取，定时为海星补充鱼食，根据计划挂机时长智能计算鱼食预算。
- **多鱼缸巡检**：依次巡检 1/2/3 鱼缸收宝与海星通用喂食，30 秒无宝石自动切缸，每小时可选魔力召唤与宝石融合，支持逐步状态播报与心跳日志。

### 2. 每日收尾（日常串联总控）
一键自动按序执行所勾选的各项日常活动，各子任务结束后安全返回主鱼缸：
- **每日免费礼包**：自动领取商城每日礼包。
- **驯鹿鱼礼物**：一键收取驯鹿鱼礼物并自动回礼。
- **乐队鱼演出**：前往游乐园邀请好友，支持最新乐章及 19 首指定乐章演出。
- **金海豚小游戏**：贝币激活启动，全屏双模板高频检测经验星，爱心自动补充，最多连续完成 3 局。
- **钓鱼达人**：星河、冰川、宫殿温泉等 6 大钓场导航，自动使用奶酪鱼饵甩杆与智能咬钩收杆。
- **浪漫满屋**：自动前往情侣鱼进行祝福。

### 3. 独立专项模块
- **开贝壳活动**：大章鱼开贝壳轮次控制，普通奖励自动继续，遇章鱼固定保留随机奖品。
- **好友摸宝**：自动巡访好友鱼缸收取金币产物，单好友上限 12 次，体力耗尽自动跳过；遇到海牛先生自动完成喂食。
- **海牛先生**：周末海牛先生独立喂食任务，支持单独定时或手动触发喂食。
- **海獭摸宝**：在目标好友间往复切换并自动摸取指定宝石。
- **宝石礼盒兑换**：从主鱼缸右下角宝箱进入，逐卡检查 7 大配方并自动兑换满每日 10/10 宝石礼盒。
- **宝石订单**：自动完成带对号的普通或特殊订单，丢弃当前不可完成订单，达到每日 10/10 后返回鱼缸。
- **购买鱼食**：金币购买廉价鱼食独立模块，支持在各级页面步骤可恢复启动。

### 4. 全局弹窗与异常防护
- 全局每日签到领奖与弹窗关闭。
- 全局特惠礼包弹窗自动关闭。
- 全局意外活动页面安全退出并返回原任务继续执行。
- 画面静止看门狗保护与任务停止响应。

### 5. 现代化桌面端与原生更新
- 基于 MFAAvalonia 的桌面 UI 交互与动态日志面板。
- 支持 GitHub 原生整包热替换一键自动更新，无需手动下载解压覆盖。

本项目只使用视觉识别和模拟点击，不读取或修改游戏封包，不提供任何付费、购买或充值操作。

## 当前测试状态与稳定性说明

- 目前观测到的最长无人工干预稳定运行时间约为 **8 小时**（未进行更长时间的连续运行测试）。
- 随着各功能状态机与全局异常弹窗处理（签到、活动页退出等）的完善，挂机稳定性显著提升。
- 长时间未查看时，仍可能受模拟器自身稳定性或网络波动影响。建议定期关注运行状态，请勿过度依赖长时间完全无人值守。

最新说明同时记录在 [RELEASE_NOTES.md](./RELEASE_NOTES.md)，并会自动附加到 GitHub Release 正文。

## 下载与使用

1. 从 [Releases](https://github.com/zhimaheiye/MaaHappyFish/releases) 下载名称包含 `MaaHappyFish-win-x86_64` 的压缩包。
2. 完整解压到一个独立目录，不要直接在压缩包内运行。（已安装支持自动更新版本的用户可直接在 MFA 客户端内一键在线升级）。
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

收集器会打包最近 3 份 MFA 界面日志、最近 3 份 MaaFramework 调试日志和最近 10 张失败现场截图。它不收集账号配置，也不会自动上传任何内容。

## 开发

源码目录与本地运行目录相互分离：

- `agent/`：Python Agent 与自定义识别、动作
- `assets/`：Project Interface、Pipeline 和图片资源
- `tools/`：资源校验与发行包组装脚本
- `client_avalonia/`：本地调试运行目录，不提交到 Git

本地开发需要 Python、`maafw` 与 Node.js。常用代码级检查：

```powershell
python dev/test_pipeline_regex.py
python dev/test_agent_registration_refs.py
python dev/test_update_contract.py
python dev/test_release_agent_imports.py
```

## 发布

GitHub Actions 会在推送 `v*` 标签后自动组装并发布各平台产物。Windows x64 包会额外内置嵌入式 Python、OpenCV 和 `maafw`。

```powershell
git tag v0.5.2
git push origin v0.5.2
```

版本号会在打包时自动写入 `interface.json`，无需手工修改。

## 免责声明

本项目与《开心水族箱》及其运营方无隶属或合作关系，仅供学习和个人自动化测试使用。使用自动化工具可能违反游戏服务条款或导致账号风险，使用者应自行判断并承担后果。

## 许可证

MaaHappyFish 自有源码使用 [MIT License](./LICENSE)。发行包包含按各自许可证分发的第三方组件，详见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。
