# MaaHappyFish 开发与发布

## 开发环境

- Windows x64
- Python 3.13 与 `maafw`
- Node.js 22+
- MuMu 模拟器 v5+，默认 ADB 地址 `127.0.0.1:16416`

本地运行入口为 `client_avalonia/MFAAvalonia.exe`。该目录只用于调试，不提交到 Git。

## 目录分工

- `assets/interface.json`：MFAAvalonia 项目、任务和选项定义
- `assets/resource/`：Pipeline、图片和 OCR 资源
- `agent/`：Python 自定义识别与动作
- `tools/install.py`：发行包组装
- `.github/workflows/install.yml`：跨平台构建和 GitHub Release

修改 `assets/interface.json` 后，需要同步到本地 `client_avalonia/interface.json`。修改 `assets/resource/` 后，本地运行目录若没有使用目录链接，也需要同步对应资源。

## 代码级检查

```powershell
npm ci
npx @nekosu/maa-tools check
python tools/validate_schema.py --schema-dir deps/tools --resource-dirs assets/resource/pipeline --interface-files assets/interface.json
python -m compileall agent tools
```

默认不执行浏览器或模拟器交互测试。涉及识别模板、坐标或完整操作链路时，由维护者在 Windows x64 + MuMu 环境中单独验证。

## 发布

普通分支推送和 Pull Request 会构建测试产物；推送 `v*` 标签会创建 GitHub Release：

```powershell
git tag v0.1.0
git push origin v0.1.0
```

Windows x64 是正式支持的发行目标，包内自带 Python 与 `maafw`。其他平台产物属于未经维护者测试的实验性构建。
