---
name: maa-release-workflow
description: >-
  MaaHappyFish 打包发布新版本、更新版本号、推送 Tag 及发布 CI 监控的完整技能工作流。
  当用户要求“打包发新版”、“发 release”、“推 tag”、“升级版本号”、“打包并推送”时激活本技能。
---

# MaaHappyFish 版本发布与打包工作流 Skill

本文档是 MaaHappyFish 项目的专属 Workspace Skill，完整定义了**版本号升级、前置静态硬门禁、交付文档同步、Git Commit/Tag、远程推送、GitHub Actions CI 监控、多平台构建核验与发布确认**的全流程标准。

> 📖 **项目文档镜像**：本文档与根目录 `docs/release-workflow.md` 保持完全同步。在项目导航地图 `AGENTS.md`、开发手册 `docs/handoff/DEVELOPMENT_PLAYBOOK.md` 及交接档案 `docs/handoff/CURRENT.md` 中均已建立显式索引。

---

## 0. 激活时机与触发条件

当用户在对话中提到：
- “打包发一个新版，应该是 0.6.x 了”
- “发 release / 发布新版本”
- “打 tag / 推送 tag”
- “升级版本到 vX.Y.Z”
- “打包并推送 X.Y.Z”

立即激活并严格遵循本技能步骤执行。

---

## 1. 发布流程全景图

```text
Step 1: 本地静态门禁与专项单测校验（Pre-Flight Gates，100% 通过方可继续）
    ↓
Step 2: 版本号升级（assets/interface.json 更新并强制同步至 client 与 client_avalonia）
    ↓
Step 3: 交付文档与交接状态闭环同步（RELEASE_NOTES / STATUS / CURRENT / ISSUES）
    ↓
Step 4: Git 暂存与检查（包含新图片素材与核心代码，严格排除临时调试文件）
    ↓
Step 5: Git Commit 与打 Tag（Conventional Commit: chore: release vX.Y.Z）
    ↓
Step 6: Git Push（先推 main 分支，后推 vX.Y.Z 标签触发 GitHub CI）
    ↓
Step 7: GitHub Actions CI 监控（-R zhimaheiye/MaaHappyFish 监听 8 平台构建与 Windows 实机硬门禁）
    ↓
Step 8: GitHub Release 产物核验（确认 8 个平台的 .zip 资产已全部上传）
    ↓
Step 9: 里程碑检查（仅限 v1.0.0 触发小红书抽奖，其余版本绝对不触发）
```

---

## 2. Step 1 — 本地静态硬门禁（Pre-Flight Gates）

**必须在提交前 100% 全部通过，严禁跳过任何一项。**

在工作目录 `d:\happyfishgame` 执行：

### 2.1 Pipeline 正则与资源加载校验
```powershell
python dev/test_pipeline_regex.py
```
- 验证所有 Pipeline 文件（29+ 个）中的 OCR `expected` 字段正则表达式合法性；
- 验证 `MaaFramework` 成功加载全部 700+ 个节点资源。

### 2.2 Agent 动作与识别引用完整性校验
```powershell
python dev/test_agent_registration_refs.py
```
- 确保 Pipeline 引用的所有 `custom_action` / `custom_recognition` 均在 Agent 中注册。

### 2.3 自动更新契约静态校验
```powershell
python dev/test_update_contract.py
```
- 验证三份 `interface.json` SHA256 完全一致；
- 验证 `github` URL 纯文本且无末尾斜杠；
- 验证 `version` 字段为合法 SemVer；
- 验证发行包文件名匹配 MFAAvalonia 优先级 100 模式 `MaaHappyFish-win-x86_64-v*.zip`。

### 2.4 发布运行时依赖冒烟校验
```powershell
python dev/test_release_agent_imports.py
```
- 验证 `maa`、`numpy`、`cv2` 及 Agent 模块在 Python 环境下导入无异常。

### 2.5 涉及修改特性的业务单测
若本版本涉及业务功能修改，运行对应单测，例如：
```powershell
python dev/test_emulator_ads.py
python dev/test_daily_magic_puzzle.py
python dev/test_princess_task.py
python dev/test_secret_realm_gate.py
python dev/test_golden_dolphin_pipeline.py
python dev/test_daily_routine_scheduler.py
```

---

## 3. Step 2 — 更新版本号（三份 interface.json 同步）

三份 `interface.json` 必须保持字节级完全一致：
1. `assets/interface.json`（源文件）
2. `client/interface.json`（手动同步）
3. `client_avalonia/interface.json`（手动同步）

### 执行命令：
1. 修改 `assets/interface.json` 中的 `"version": "X.Y.Z"`（纯 SemVer 数字，不带 `v` 前缀）。
2. 在 PowerShell 中覆盖同步到另外两份：
   ```powershell
   Copy-Item assets\interface.json client\interface.json -Force
   Copy-Item assets\interface.json client_avalonia\interface.json -Force
   ```
3. 重新运行门禁确认一致：
   ```powershell
   python dev/test_update_contract.py
   ```

---

## 4. Step 3 — 交付文档与交接状态同步

### 4.1 更新 `RELEASE_NOTES.md`
在文件顶部插入本次发布的更新说明：
```markdown
## vX.Y.Z 更新内容

- **功能名称/优化项**：具体说明...
- **分发说明**：Windows x64 发行包继续内置 Python 3.13.5、MaaFramework 与 Agent，已安装用户可通过 MFAAvalonia 原生 GitHub 在线更新无缝升级至 vX.Y.Z。

## 历史版本更新
```

### 4.2 更新 `PROJECT_STATUS.md`
- **版本**：更新为新正式版本号（如 `v0.6.3`）
- **commit**：更新为新版本号（如 `v0.6.3`）
- **发布时间**：更新为发版日期（如 `2026-09-21`）
- **尚未正式发布**：若全量发布则写 `暂无`

### 4.3 更新 `docs/handoff/CURRENT.md`
- 更新表格中的 `Current version`（如 `0.6.3`）
- 更新 `Latest release` 链接（如 `[v0.6.3](https://github.com/zhimaheiye/MaaHappyFish/releases/tag/v0.6.3)`）

### 4.4 检查 `ISSUES.md` 闭环
已修复的 Bug 从待修复列表移除并迁移为已完成记录，不得遗留失效待办。

---

## 5. Step 4 — Git 暂存与检查

```powershell
git status --short
```
- 核查未跟踪文件（`??`），确保新增图片素材（`assets/resource/image/*.png`）与新增 Agent/开发脚本已纳入；
- 坚决排除临时截图、排查日志等非工程资产；
- 执行暂存：
  ```powershell
  git add -A
  git status
  ```

---

## 6. Step 5 — Git Commit 与打 Tag

```powershell
# 1. 提交发布 Commit
git commit -m "chore: release vX.Y.Z"

# 2. 打发布 Tag（必须带小写 v 前缀）
git tag vX.Y.Z
```

---

## 7. Step 6 — 推送到 GitHub 远程仓库

```powershell
# 1. 推送主分支提交
git push origin main

# 2. 推送发布 Tag（真正触发 GitHub Actions 发布流程）
git push origin vX.Y.Z
```

---

## 8. Step 7 — GitHub Actions CI 监控与核验

### 8.1 仓库限定约束（强制遵守）
**所有 `gh` 命令必须显式带上 `-R zhimaheiye/MaaHappyFish` 参数！** 防止 `gh` 回退到 upstream 模板库导致操作失败。

### 8.2 监控 CI 流程
```powershell
# 1. 查询当前运行
gh run list -R zhimaheiye/MaaHappyFish --limit 5

# 2. 持续监听运行状态直至完成
gh run watch <RUN_ID> -R zhimaheiye/MaaHappyFish
```

### 8.3 核心 Job 检查清单
- [ ] 8 个平台的 `install` 构建矩阵全部绿色通过；
- [ ] `verify (win, x86_64)` CI 实机嵌入式 Python 依赖与更新契约硬门禁绿色通过；
- [ ] `changelog` 自动拼接完成；
- [ ] `release` 任务绿色通过。

---

## 9. Step 8 — GitHub Release 产物确认

```powershell
gh release view vX.Y.Z -R zhimaheiye/MaaHappyFish --json assets,name,tagName,isPrerelease,url
```

### 核验要求：
- [ ] `isPrerelease` 状态为 `false`；
- [ ] `assets` 完整包含全部 **8 个平台的 `.zip` 压缩包**：
  - `MaaHappyFish-win-x86_64-vX.Y.Z.zip`（含内嵌 Python，约 227MB）
  - `MaaHappyFish-win-aarch64-vX.Y.Z.zip`
  - `MaaHappyFish-macos-x86_64-vX.Y.Z.zip`
  - `MaaHappyFish-macos-aarch64-vX.Y.Z.zip`
  - `MaaHappyFish-linux-x86_64-vX.Y.Z.zip`
  - `MaaHappyFish-linux-aarch64-vX.Y.Z.zip`
  - `MaaHappyFish-android-x86_64-vX.Y.Z.zip`
  - `MaaHappyFish-android-aarch64-vX.Y.Z.zip`
- [ ] 状态均为 `uploaded`。

---

## 10. Step 9 — 里程碑触发门禁 (v1.0.0 Only)

- 仅当版本号达到 `1.0.0` 时触发执行 `docs/v1.0-rednote-lottery.md`；
- 所有 `0.x.x` 阶段绝对不得触发。
