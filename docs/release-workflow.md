# MaaHappyFish 版本发布与打包工作流 (Release Workflow)

本文档是 MaaHappyFish 项目标准的发版技能手册（Skill Document）。当需要**升级版本号、打包发版、打 Tag、推送 Release** 时，所有 Agent 和开发者必须严格遵循本工作流执行。

---

## 0. 触发条件与快速导航

### 什么时候查阅本手册？
当用户或任务提出以下需求时立即激活本流程：
- “打包发一个新版，应该是 0.6.x 了”
- “发 release / 发布新版本”
- “打 tag / 推送 tag”
- “升级版本到 vX.Y.Z”

### 核心文档路由
| 关联文档 | 关系说明 |
| :--- | :--- |
| `AGENTS.md` | 项目总导航地图，在“文档路由表”和“硬规则”中强制引用本文档 |
| `docs/handoff/DEVELOPMENT_PLAYBOOK.md` | 开发手册，在“检查清单”与“文档信息优先级”中引用本文档 |
| `docs/handoff/CURRENT.md` | 当前交接档案，在“Release health”与版本状态中展示最新发布产物 |
| `PROJECT_STATUS.md` | 记录当前正式版本号、commit hash 与发布日期 |
| `RELEASE_NOTES.md` | 手写维护用户可见的 Release 说明，CI 会自动拼接入 GitHub Release 正文 |
| `.agents/skills/maa-release-workflow/SKILL.md` | Antigravity 专属 Workspace Skill 镜像，提供原生技能感知与渐进式调度 |

---

## 1. 发布流程全景图

```text
Step 1: 本地静态门禁与专项单测校验（Pre-Flight Gates）
    ↓
Step 2: 版本号升级（interface.json × 3 份保持字节级一致）
    ↓
Step 3: 交付文档与交接状态闭环同步（RELEASE_NOTES / STATUS / CURRENT / ISSUES）
    ↓
Step 4: Git 暂存与检查（包含新图片/代码，剔除临时文件）
    ↓
Step 5: Git Commit 与打 Tag（Conventional Commit: chore: release vX.Y.Z）
    ↓
Step 6: Git Push（先推送 main 分支，后推送 tag 触发 CI）
    ↓
Step 7: GitHub Actions CI 监控（-R zhimaheiye/MaaHappyFish 监听 8 平台构建与 Windows 实机硬门禁）
    ↓
Step 8: GitHub Release 产物核验（确认 8 个平台的 .zip 资产已全部上传）
    ↓
Step 9: 里程碑检查（仅限 v1.0.0 触发小红书抽奖，其余版本绝对不触发）
```

---

## 2. Step 1 — 本地静态硬门禁（Pre-Flight Gates）

**必须 100% 全部通过后，才允许进入后续版本号修改与提交步骤。**

在项目根目录（`d:\happyfishgame`）打开终端依次执行：

### 2.1 Pipeline 正则与资源加载校验
```powershell
python dev/test_pipeline_regex.py
```
- **检查内容**：全量扫描 `assets/resource/pipeline/**/*.json` 中所有 OCR `expected` 字段的正则表达式语法，并通过 `MaaFramework` 底层真实加载全部节点资源（当前应成功载入 700+ 个节点）。
- **常见隐患**：OCR 内容含有未转义括号（如 `(`），会被 `std::regex` 编译失败导致整包资源加载崩溃。

### 2.2 Agent 动作与识别引用完整性校验
```powershell
python dev/test_agent_registration_refs.py
```
- **检查内容**：确保所有流水线中声明的 `custom_action` 与 `custom_recognition`，在 `agent/main.py`、`agent/my_action.py` 和 `agent/my_reco.py` 中均有对应实现与注册，禁止悬空引用。

### 2.3 自动更新契约静态校验
```powershell
python dev/test_update_contract.py
```
- **检查内容**：
  1. `assets/interface.json`、`client/interface.json`、`client_avalonia/interface.json` 三份文件 SHA256 完全一致；
  2. `github` 字段为纯文本 URL `"https://github.com/zhimaheiye/MaaHappyFish"`（无末尾斜杠）；
  3. `version` 字段为合法 SemVer（如 `0.6.3`，不带 `v` 前缀）；
  4. Release 资产名匹配 MFAAvalonia 优先级 100 规则 `MaaHappyFish-win-x86_64-v*.zip`；
  5. 首次安装预设与任务选项配置合法。

### 2.4 发布运行时依赖冒烟校验
```powershell
python dev/test_release_agent_imports.py
```
- **检查内容**：验证 `maa`、`numpy`、`cv2` 及 Agent 下的所有模块（`runtime_state`, `param_utils`, `puzzle_*`, `my_action`, `my_reco`）可被正常无错误导入。

### 2.5 涉及新特性的业务单测
若本版本修改了具体业务功能，必须同步运行对应的单元测试确保逻辑闭环，例如：
```powershell
# 按修改模块选择运行：
python dev/test_emulator_ads.py
python dev/test_daily_magic_puzzle.py
python dev/test_princess_task.py
python dev/test_secret_realm_gate.py
python dev/test_golden_dolphin_pipeline.py
python dev/test_daily_routine_scheduler.py
```

---

## 3. Step 2 — 版本号升级（interface.json × 3 份同步）

`interface.json` 中的 `version` 字段是客户端显示与更新检测的核心依据。项目内共有三处副本，**必须保持字节级完全一致**：

1. 源文件：`assets/interface.json`
2. 客户端副本：`client/interface.json`
3. 桌面端副本：`client_avalonia/interface.json`

> **注意**：`client_avalonia/resource` 是 junction 符号链接，但根目录的 `interface.json` 不在链接内，必须手动同步。

### 执行步骤：
1. 编辑 `assets/interface.json` 中的 `version` 字段为新版本号（如 `"0.6.3"`，注意纯数字，无 `v` 前缀）。
2. 在 PowerShell 中执行强制覆盖同步：
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
`RELEASE_NOTES.md` 位于项目根目录，是手写维护的更新日志。GitHub Actions CI 在发布时会使用 `git-cliff` 将其拼接在自动生成的 Changelog **之前**，直接呈现在 GitHub Release 页面顶部。

**操作要求**：在文件顶部的 `> MaaHappyFish 仍处于早期测试阶段。` 下方，插入新版本的说明块：
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
- **尚未正式发布**：若本次全量发布则更新为 `暂无`

### 4.3 更新 `docs/handoff/CURRENT.md`
- 更新表格中的 `Current version`（如 `0.6.3`）
- 更新 `Latest release` 链接（如 `[v0.6.3](https://github.com/zhimaheiye/MaaHappyFish/releases/tag/v0.6.3)`）

### 4.4 检查 `ISSUES.md` 闭环
若本版本修复了某些问题，按照硬规则执行文档闭环：从“待修复”待办中移除，迁移至已完成记录，不得遗留失效待办。

---

## 5. Step 4 — Git 暂存与检查

在提交前，务必执行：
```powershell
git status --short
```
- **仔细核对新增文件（`??`）**：新增的图片素材（`assets/resource/image/*.png`）、新增的脚本或 Agent 辅助模块（`agent/*.py`）必须纳入暂存；
- **排查临时文件**：临时的截屏测试图、现场日志、排查脚本等临时资产绝对不得误提交；
- 执行全部暂存：
  ```powershell
  git add -A
  git status
  ```

---

## 6. Step 5 — Git Commit 与打 Tag

遵循 Conventional Commits 提交规范，以便 `git-cliff` 自动提取提交日志：

```powershell
# 1. 提交发布 Commit
git commit -m "chore: release vX.Y.Z"

# 2. 打发布 Tag（必须带小写 v 前缀）
git tag vX.Y.Z
```

**Tag 命名约定**：
- 正式版：`v0.6.3`（触发正式 Release）
- 预发布：`v0.6.3-beta.1`、`v0.6.3-rc.1`（CI 会自动标记为 Pre-release）

---

## 7. Step 6 — 推送到 GitHub 远程仓库

发版流程需要推送两次：**主分支提交**与**发布 Tag**。

```powershell
# 1. 推送主分支代码
git push origin main

# 2. 推送发布 Tag（这一步真正触发 GitHub Actions 发布流水线）
git push origin vX.Y.Z
```

> **重要提醒**：仅推送分支只会触发普通代码构建校验，**只有推送 `v*` 格式的 tag 才会激活 GitHub Release 自动发版流程**。

---

## 8. Step 7 — GitHub Actions CI 监控与核验

### 8.1 仓库范围限定（极其关键！）
**执行任何 `gh` 命令时，必须显式带上 `-R zhimaheiye/MaaHappyFish` 参数！**
若省略 `-R` 参数，GitHub CLI 会回退匹配到上游模板库 `MaaXYZ/MaaPracticeBoilerplate`，导致查询不到任务或权限报错。

### 8.2 查询与监听 CI 构建
```powershell
# 1. 查看当前正在运行的 Release 任务
gh run list -R zhimaheiye/MaaHappyFish --limit 5

# 2. 持续监听指定运行（使用上述返回的 RUN_ID）
gh run watch <RUN_ID> -R zhimaheiye/MaaHappyFish
```

### 8.3 CI 核心流水线各 Job 验证清单
GitHub Actions `.github/workflows/install.yml` 包含以下关键阶段：
1. **`meta`**：从 tag 解析版本号，校验正式版/预发布标记；
2. **`install`（8 个并行构建矩阵）**：
   - 跨平台覆盖：`os=[win, macos, linux, android]` × `arch=[x86_64, aarch64]` 共 8 组；
   - 依赖集成：下载 MaaFramework 核心库与 MFAAvalonia 客户端；
   - Windows x64 专属打包：自动注入嵌入式 Python 3.13.5，pip 安装 `maafw` 与 `opencv-python-headless`，生成运行环境；
3. **`verify (win, x86_64)`（CI 实机硬门禁）**：
   - 在真实 Windows Runner 上解包构建产物；
   - 运行内嵌 Python 真实执行 `import maa`, `import cv2`, `import numpy` 及 Agent 模块冒烟测试；
   - 运行 `test_update_contract.py` 校验整包结构；
   - 此 Job 失败将阻断 Release 发布！
4. **`changelog`**：结合 `RELEASE_NOTES.md` 与 Git 提交生成发布说明；
5. **`release`**：将 8 个平台的发布压缩包上传至 GitHub Release。

---

## 9. Step 8 — GitHub Release 产物确认

CI 流程全绿通过后，通过命令行验证 Release 产物状态：

```powershell
gh release view vX.Y.Z -R zhimaheiye/MaaHappyFish --json assets,name,tagName,isPrerelease,url
```

### 必达核验项：
- [ ] `isPrerelease` 状态符合预期（正式版为 `false`）；
- [ ] `assets` 列表中必须完整包含 **8 个平台的 `.zip` 压缩包**：
  1. `MaaHappyFish-win-x86_64-vX.Y.Z.zip`（包含嵌入式 Python 环境，体积约 227MB）
  2. `MaaHappyFish-win-aarch64-vX.Y.Z.zip`
  3. `MaaHappyFish-macos-x86_64-vX.Y.Z.zip`
  4. `MaaHappyFish-macos-aarch64-vX.Y.Z.zip`
  5. `MaaHappyFish-linux-x86_64-vX.Y.Z.zip`
  6. `MaaHappyFish-linux-aarch64-vX.Y.Z.zip`
  7. `MaaHappyFish-android-x86_64-vX.Y.Z.zip`
  8. `MaaHappyFish-android-aarch64-vX.Y.Z.zip`
- [ ] 所有资产 `state` 字段为 `uploaded`。

---

## 10. Step 9 — 里程碑与边界检查 (v1.0.0 Only)

- **唯一触发条件**：当且仅当项目版本号正式达到 **`1.0.0`**（工具 1.0 版本正式完结大版本发布）时，才触发查阅并执行 `docs/v1.0-rednote-lottery.md` 中约定的小红书抽奖活动流程。
- **严格禁止提前触发**：当前所有 `0.x.x` 阶段，任何 Agent 或自动化工作流**绝对不得提前触发或执行该文件**。

---

## 11. 常见错误排查与应急手册

| 常见错误 / 现象 | 根因分析 | 应急处理与预防措施 |
| :--- | :--- | :--- |
| **`std::regex` 编译失败** (`Unmatched parenthesis`) | Pipeline 中的 OCR `expected` 字段包含未转义的 `(` 等正则字符 | 改用不含特殊字符的稳定中文语义关键词（如“刷新体力”），或使用 `\\(` 双重转义；发版前必跑 `python dev/test_pipeline_regex.py` |
| **Agent 注册引用缺失** | Pipeline 中调用了未在 `my_action.py`/`my_reco.py` 注册的名称 | 运行 `python dev/test_agent_registration_refs.py` 检查并补齐注册代码 |
| **更新契约校验失败** | 只修改了 `assets/interface.json`，遗漏了 `client/` 或 `client_avalonia/` 副本 | 重新执行 `Copy-Item` 强制覆盖，确保三份文件 SHA256 字节完全一致 |
| **CI 未触发 Release 任务** | 仅推送了 `main` 分支提交，忘记推送 Tag | 执行 `git push origin vX.Y.Z` 推送对应标签 |
| **`verify (win, x86_64)` 失败** | 新增的第三方 Python 依赖未写入 `agent/requirements-release.txt` 或嵌入式脚本漏检 | 补齐 `requirements-release.txt`，检查 `.github/workflows/install.yml` 中的 `$required` 文件列表 |
| **`gh` 报 404 或找不到运行** | 未指定仓库，`gh` 默认落入 upstream 模板库 | 始终附加 `-R zhimaheiye/MaaHappyFish` 参数 |
