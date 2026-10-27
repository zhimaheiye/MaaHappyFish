# 主开发机环境

2026-10-24 迁移记录。本机主仓库为 `D:\happyfishgame`，探索证据仓库为
`D:\开心水族箱活动经验\happyfishagent`。历史文档中的 `D:\happyfishagent`
在本机应映射到后者，不创建兼容目录、不移动证据仓库。

## Python 与启动入口

项目专用解释器：`D:\happyfishgame\.venv\Scripts\python.exe`，Python 3.13.7 x64。
MaaFw 固定为 5.12.3，与开发客户端自带原生 MaaFramework v5.12.3 一致。
OpenCV headless 4.12.0.88、NumPy 2.2.6；完整开发依赖见
`tools/requirements-dev.txt`。系统 Python 保持原有依赖，避免影响其它项目。

重建环境：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools/requirements-dev.txt
```

开发时使用 `tools/start-dev-client.cmd` 启动客户端。它只为子进程把
`.venv\Scripts` 放到 PATH 前面，使三份 interface.json 中的 `child_exec: python`
选中项目解释器。直接双击 MFAAvalonia.exe 会使用系统 PATH，不能保证选中此环境。
VS Code 默认解释器也已指向 `.venv`。

2026-10-26，D 盘根目录的 `Run-MaaHappyFish.bat` → `Start-MaaHappyFish.ps1`
启动链已改为启动 `D:\happyfishgame\client_avalonia\MFAAvalonia.exe`，工作目录为
开发客户端目录，并仅为子进程设置 `.venv\Scripts` PATH 与 `VIRTUAL_ENV`。
进程检测同时核对名称和完整路径；脚本的原有模拟器启动、参数及配置只读校验逻辑保留。
原脚本备份为 `D:\Start-MaaHappyFish.ps1.bak.dev-client-20261026-132101`。
此次只做 PowerShell 语法、目标文件及 Junction 检查，未运行启动脚本或重启客户端。

`client_avalonia/agent` Junction 指向仓库 `agent`；`client_avalonia/resource`
Junction 指向 `assets/resource`。接口源文件仍为 `assets/interface.json`，与已有
`client/interface.json`、`client_avalonia/interface.json` 字节一致，版本以源文件为准。
同步接口及图标使用 `tools/sync_dev_client.ps1`。

开发实例只修正旧 MuMu 安装路径为 `D:/MuMuPlayer`。设备序列号
`127.0.0.1:16384`、截图方式和任务选项保留，未探测设备或连接模拟器。
正式挂机目录 `D:\MaaHappyFish-win-x86_64-v0.4.4` 保留独立运行。

## 备份与验证边界

迁移前 Git 状态、stash、6131 个受保护文件的 SHA256、搬来的 Agent/Resource
目录和原客户端配置保存在 `temp/migration-20261024/`，本轮保留备查。
Codex 配置备份为用户目录 `.codex/config.toml.pre-fastctx-20261024`。

FastCTX 0.2.6 已以本地 stdio MCP 注册，启用 Bash 工具并指定 Git Bash；
已完成协议握手、文件读取和 `pip check` 调用。原有其它 MCP 配置已保留。
当前聊天未动态加载其工具，新聊天或重启 MCP 连接后使用。

代码级通过：Pipeline 309 条正则及 975 节点原生加载、Agent 注册引用和导入、
更新契约、JSON Schema、全局弹窗、统一收宝、日常配置复用 9 项（含无设备跨进程
Agent 测试）、日常调度器、定时器 10 项、Python 编译与 pip check。
没有启动开发客户端、模拟器或游戏任务；本次导入检查使用开发虚拟环境，
不等同于新的发行包 embedded Python 验收。

迁移期间曾发现源码图片和历史探索图片缺失。正式模板已按迁移前 SHA256 恢复；
历史探索素材的恢复清单保存在上述备份目录的 `recovery*.json`。
缺失来源尚未确认。最后一次完整核对：4910 个文件内容不变，仅开发实例配置的
两处旧路径发生预期变更；仍缺 1220 个历史文件，合计 1,086,739,585 字节。
两仓 HEAD、暂存内容与 stash 均保持迁移前状态，Git connectivity 检查通过。
正式模板为 148 张可解码 PNG 加原有 1 字节 `empty.png` 占位文件。
额外 maa-tools 检查曾在图片缺失时失败，不计入通过项。
2026-10-24 用户确认：缺失的历史素材不再补齐，后续开发需要时重新采集保存。
此项不再作为恢复待办或迁移阻断。按该确认，开发环境迁移已完成；
验证范围为上述代码级检查，尚未做 MFA／模拟器实机验收。
