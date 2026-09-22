# MaaHappyFish 版本发布与打包工作流 (Release Workflow)

> 📌 **单一事实源声明 (Single Source of Truth)**：本文档是 MaaHappyFish 项目版本发布、打包、打 Tag、CI 监控与资产核验的**唯一权威流程正文**。`.agents/skills/maa-release-workflow/SKILL.md` 仅作为 Antigravity 调度的薄入口，发版执行一律以本文档为准。

---

## 0. 触发条件与核心安全红线

### 什么时候查阅本手册？
当用户或任务提出以下需求时立即激活并执行本流程：
- “打包发一个新版，应该是 0.6.x 了”
- “发 release / 发布新版本”
- “打 tag / 推送 tag”
- “升级版本到 vX.Y.Z”

### 核心安全红线：
1. **单一事实源**：一切规则与步骤以本文档为准，严禁在其他地方维护平行发版逻辑；
2. **严禁覆盖既有版本**：已发布的 Tag / Release 绝对禁止删除、覆盖、移动或强制重建；
3. **两阶段状态沉淀**：Tag 推送前严禁提前谎报“已正式发布”；只有当 CI 构建全绿且资产核验完整后，才作为 post-release 提交更新状态；
4. **仓库严格限定**：所有 `gh` 命令必须显式附加 `-R zhimaheiye/MaaHappyFish` 参数，防止回退到上游模板库；
5. **严禁盲目暂存**：严禁无脑执行 `git add -A`，暂存前后必须核查未跟踪文件与 `git diff --cached`。

---

## 1. 发布流程全景图

```text
Step 0: Git 环境与分支安全前置核验（main 分支、无分叉、Tag 不存在）
    ↓
Step 1: 本地静态硬门禁与专项单测（Pre-Flight Gates，100% 通过方可继续）
    ↓
Step 2: 升级 canonical 版本号（assets/interface.json，若存在则同步本地 client 目录）
    ↓
Step 3: 第一阶段：Tag 前文档与代码准备（RELEASE_NOTES.md / ISSUES.md 闭环，不提前改 STATUS）
    ↓
Step 4: 审慎 Git 暂存与检查（包含必要资产，严格排除临时排查文件）
    ↓
Step 5: Git Commit 与打 Tag（Conventional Commit: chore: release vX.Y.Z，Tag 格式: vX.Y.Z）
    ↓
Step 6: 双阶段 Git Push（先推 main 分支提交，后推 vX.Y.Z 标签触发 GitHub CI）
    ↓
Step 7: GitHub Actions CI 精准监控（过滤 Tag 对应 Run ID，防止选错 main push 的竞态 Run）
    ↓
Step 8: GitHub Release 产物核验（确认 4 个 OS × 2 个架构共 8 个构建目标产物完整上传）
    ↓
Step 9: 第二阶段：Post-Release 文档状态确认（提交 PROJECT_STATUS.md 与 CURRENT.md 正式状态）
    ↓
Step 10: 里程碑检查（仅限 v1.0.0 触发小红书抽奖，本地文档不存在时不得猜测）
```

---

## 2. Step 0 — Git 环境与分支安全前置核验

在修改任何文件之前，在项目仓库根目录（可通过 `git rev-parse --show-toplevel` 确认）执行检查：

```powershell
git status --short
git branch --show-current
git remote -v
git fetch origin --tags
git rev-list --left-right --count origin/main...HEAD
```

### 必须满足的硬性标准：
1. **当前分支必须为 `main`**：`git branch --show-current` 输出必须是 `main`。严禁在功能分支或处于分离头指针（detached HEAD）状态下发版；
2. **`origin` 远端必须正确**：`git remote -v` 中 `origin` 的 push URL 必须为 `https://github.com/zhimaheiye/MaaHappyFish.git`；
3. **工作区不得有来源不明的修改**：若存在未知变更，必须立即停下向用户确认，绝对禁止私自静默暂存或清理；
4. **分支同步确定性门禁（严格要求 `0    0`）**：
   运行 `git rev-list --left-right --count origin/main...HEAD`，输出格式为 `<behind> <ahead>`：
   - **`0    0`**：本地与远端完全同步，允许继续；
   - **本地仅落后（behind > 0, ahead == 0）且工作区干净（`git status --short` 无输出）**：可以执行 `git pull --ff-only origin main` 快进同步，拉取后重新执行本门禁核验；
   - **其余情况（本地存在未推送提交 ahead > 0、与远端存在分叉、或需要非 fast-forward 合并）**：必须立即停止发版并向用户报告，绝对严禁使用 force push、rebase 或 hard reset 强行同步；
5. **目标 Tag 全局不存在**：
   - 本地检查：`git tag -l vX.Y.Z` 必须无输出；
   - 远端检查：`git ls-remote --tags origin refs/tags/vX.Y.Z` 必须无输出；
   - Release 检查：`gh release view vX.Y.Z -R zhimaheiye/MaaHappyFish` 必须返回未找到（not found）；
   - 若目标 Tag 或 Release 已存在，**立即终止流程**，严禁覆盖、删除或重新打同名 Tag。

---

## 3. Step 1 — 本地静态硬门禁（Pre-Flight Gates）

**必须 100% 全部通过后，才允许进入后续版本号修改与提交步骤。**

在项目仓库根目录下依次执行：

### 3.1 Pipeline 正则与资源加载校验
```powershell
python dev/test_pipeline_regex.py
```
- **检查内容**：扫描全部 Pipeline 文件中的 OCR `expected` 正则语法，并通过 `MaaFramework` 底层真实加载全部节点资源；
- **事故预防**：杜绝未转义的 `(` 等字符导致 `std::regex` 编译失败引发整包资源加载崩溃。

### 3.2 Agent 动作与识别引用完整性校验
```powershell
python dev/test_agent_registration_refs.py
```
- **检查内容**：确保所有流水线中声明的 `custom_action` 与 `custom_recognition`，在 `agent/main.py`、`agent/my_action.py` 和 `agent/my_reco.py` 中均有对应实现与注册，禁止悬空引用。

### 3.3 自动更新契约静态校验
```powershell
python dev/test_update_contract.py
```
- **真实契约逻辑**：
  1. `assets/interface.json` 是 Git 跟踪的唯一 canonical source；
  2. `client/interface.json` 与 `client_avalonia/interface.json` 为 `.gitignore` 忽略的本地运行目录。`test_update_contract.py` **仅在这两个本地目录/文件实际存在时**才执行 SHA256 校验；干净的 clone 不要求这两个本地目录存在；
  3. `github` 字段必须严格等于 `"https://github.com/zhimaheiye/MaaHappyFish"`（纯文本，无末尾斜杠）；
  4. `version` 字段为合法 SemVer（`^\d+\.\d+\.\d+$`，不带 `v` 前缀）；
  5. 发行包文件名格式需匹配 MFAAvalonia 优先级 100 正则规则。

### 3.4 发布运行时依赖冒烟校验
```powershell
python dev/test_release_agent_imports.py
```
- **检查内容**：在 Python 环境下验证 `maa`, `numpy`, `cv2` 及 Agent 模块能正常无报错导入。

### 3.5 涉及修改特性的业务单测
若本版本涉及具体业务功能改动，必须运行对应单元测试确保逻辑闭环（如 `test_emulator_ads.py`, `test_daily_magic_puzzle.py`, `test_princess_task.py`, `test_secret_realm_gate.py`, `test_daily_routine_scheduler.py` 等）。

---

## 4. Step 2 — 升级版本号与可选本地副本同步

### 4.1 更新 canonical 源文件
编辑 `assets/interface.json` 中的 `version` 字段为新版本号（如 `"0.6.3"`，纯数字，无 `v` 前缀）。

### 4.2 同步存在的本地客户端目录（带存在性判断）
在 PowerShell 中执行前检查目录是否存在，避免在干净 clone 或未部署客户端的机器上因目录缺失而报错：
```powershell
if (Test-Path client) { Copy-Item assets\interface.json client\interface.json -Force }
if (Test-Path client_avalonia) { Copy-Item assets\interface.json client_avalonia\interface.json -Force }
```
重新运行门禁确认一致：
```powershell
python dev/test_update_contract.py
```

---

## 5. Step 3 — 发布第一阶段：Tag 前文档更新 (Pre-Tag)

在打 Tag 与推送之前，仅更新本次版本必须包含的内容，**严禁提前将尚未构建发布的版本写入正式发布状态**：

### 5.1 更新 `RELEASE_NOTES.md`
在 `RELEASE_NOTES.md` 中，将新的 `vX.Y.Z` 更新块插入文件中从顶部开始遇到的第一个 `## 历史版本更新` 标题之前（严禁重写或修改其后的历史段落，严禁每个版本重复新建“## 历史版本更新”标题以防标题堆叠）：

```markdown
## vX.Y.Z 更新内容

- **功能名称/优化项**：具体说明...
- **分发说明**：Windows x64 发行包继续内置 Python 3.13.5、MaaFramework 与 Agent，已安装用户可通过 MFAAvalonia 原生 GitHub 在线更新无缝升级至 vX.Y.Z。

## 历史版本更新
```

### 5.2 暂缓更新发布状态文件
- **`PROJECT_STATUS.md` 与 `docs/handoff/CURRENT.md` 在此阶段保持不变**；
- 不得提前把一个尚不存在的 Release 写成“当前正式版已发布”。只有当 CI 跑通、GitHub Release 生成且资产核验完整后，才作为 Post-Release 提交确认。

### 5.3 检查 `ISSUES.md` 闭环
将本次已完成代码级验证的 Bug 迁移为已完成记录，或从待修复待办中移除。

---

## 6. Step 4 — 审慎 Git 暂存与检查

**严禁盲目直接执行 `git add -A`**。必须显式核对未跟踪文件和暂存差异：

```powershell
# 1. 检查修改与未跟踪文件
git status --short

# 2. 审慎添加（确保新图片、新脚本被包含，排查日志和临时文件被排除）
git add <必要文件> # 或在确认工作区完全无多余杂质后 git add -A

# 3. 严格复核暂存区
git status
git diff --cached --stat
git diff --cached
```

---

## 7. Step 5 — Git Commit 与打 Tag

遵循 Conventional Commits 提交规范，以便 `git-cliff` 自动提取提交日志：

```powershell
# 1. 提交发布 Commit
git commit -m "chore: release vX.Y.Z"

# 2. 打发布 Tag（必须带小写 v 前缀）
git tag vX.Y.Z
```

> **说明**：当前项目发布规范专注定义正式版本（`vX.Y.Z`），不维护未完整约定的预发布（beta/rc）流程。

---

## 8. Step 6 — 双阶段 Git 推送

发版流程需要两阶段推送：

```powershell
# 1. 先推送 main 分支提交
git push origin main

# 2. 再推送发布 Tag（真正触发 GitHub Actions 的 Release 流水线）
git push origin vX.Y.Z
```

> **重要提醒**：仅推送分支只会触发普通代码构建校验，**只有推送 `v*` 格式的 tag 才会激活 GitHub Release 自动发版流程**。

---

## 9. Step 7 — GitHub Actions CI 监控（防选错竞态）

### 9.1 必须显式指定仓库
**所有 `gh` 命令必须带 `-R zhimaheiye/MaaHappyFish`**，防止默认落入上游模板库。

### 9.2 识别并监控 Tag Push 对应的 Workflow Run
由于 `git push origin main` 与 `git push origin vX.Y.Z` 会先后触发 `install.yml`，列表中会出现两个接近的 Run。**绝对不能盲目抓取最新的一条，必须确认其 ref 为目标 Tag！**

```powershell
# 查看 install.yml 最近运行，核对 HEAD BRANCH / TAG 列必须为目标 vX.Y.Z
gh run list -R zhimaheiye/MaaHappyFish -w install.yml --limit 5

# 或通过 jq 精确过滤对应 Tag 的 Run ID：
gh run list -R zhimaheiye/MaaHappyFish -w install.yml --json databaseId,headBranch,event,status --jq '.[] | select(.headBranch=="vX.Y.Z") | .databaseId'
```

获取到对应的 `<RUN_ID>` 后，启动监听：
```powershell
gh run watch <RUN_ID> -R zhimaheiye/MaaHappyFish
```

### 9.3 CI 构建矩阵与硬门禁核查清单
- **`install`（4 个 OS × 2 个架构，共 8 个构建目标）**：全部绿色通过（`win/macos/linux/android` × `x86_64/aarch64`）；
- **`verify (win, x86_64)`**：GitHub Windows Runner 上的发行包硬门禁 / embedded Python smoke gate 必须绿色通过；
- **`changelog` 与 `release`**：全部成功执行。

---

## 10. Step 8 — GitHub Release 产物核验

CI 结束后，查询 GitHub Release 资产：

```powershell
gh release view vX.Y.Z -R zhimaheiye/MaaHappyFish --json assets,name,tagName,isPrerelease,url
```

### 资产核验项：
1. `isPrerelease` 必须为 `false`；
2. `assets` 完整包含全部 **4 个 OS × 2 个架构共 8 个构建目标的 `.zip` 压缩包**：
   - `MaaHappyFish-win-x86_64-vX.Y.Z.zip`（当前参考值：约 227MB，内嵌 Python 运行环境；参考值非长期固定契约）
   - `MaaHappyFish-win-aarch64-vX.Y.Z.zip`
   - `MaaHappyFish-macos-x86_64-vX.Y.Z.zip`
   - `MaaHappyFish-macos-aarch64-vX.Y.Z.zip`
   - `MaaHappyFish-linux-x86_64-vX.Y.Z.zip`
   - `MaaHappyFish-linux-aarch64-vX.Y.Z.zip`
   - `MaaHappyFish-android-x86_64-vX.Y.Z.zip`
   - `MaaHappyFish-android-aarch64-vX.Y.Z.zip`
3. 所有资产状态均为 `uploaded`。

---

## 11. Step 9 — 发布第二阶段：Post-Release 文档状态确认 (Post-Release)

在确认 GitHub Release 已正式上线并可下载后，再将项目交接状态正式更新为已发布：

### 11.1 更新发布状态
1. **`PROJECT_STATUS.md`**：
   - 更新当前正式版为 `vX.Y.Z`，commit 字段记录为 `vX.Y.Z`（遵循项目既有惯例 `commit：vX.Y.Z`，不擅自改成 Git 完整 commit hash），发布时间为当前日期；
   - 尚未正式发布：`暂无`。
2. **`docs/handoff/CURRENT.md`**：
   - 更新 `Current version` 为 `X.Y.Z`；
   - 更新 `Latest release` 为最新 GitHub Release 链接；
   - `Release health` 保持正常，使用相对链接 `../release-workflow.md`。

### 11.2 提交状态更新
```powershell
git add PROJECT_STATUS.md docs/handoff/CURRENT.md
git commit -m "docs: confirm vX.Y.Z release status"
git push origin main
```

---

## 12. Step 10 — 里程碑边界检查 (v1.0.0 Only)

- `docs/v1.0-rednote-lottery.md` 已在 `.gitignore` 中标记为维护者本机私有/本地里程碑文档；
- **触发条件**：当且仅当版本号达到 `1.0.0` 时触发；当前所有 `0.x.x` 版本绝对不触发；
- **容错防线**：若该文件在当前工作区不存在，**严禁自行猜测或造假生成抽奖流程**，只能报告本地文档不可用。

---

## 13. 第三方运行时依赖边界与核查要求

当前 GitHub Actions `install.yml` 在 Windows x64 打包阶段**实际硬编码**通过 pip 安装以下包：
```powershell
maafw opencv-python-headless
```
并没有直接通过 `-r agent/requirements-release.txt` 自动读取依赖。
因此：**绝不能声称“只要在 requirements-release.txt 加一行，发行包就会自动包含该依赖”**。

新增运行时第三方依赖时必须四步核查闭环：
1. 更新 `agent/requirements-release.txt` 声明版本；
2. 检查并同步修改 `.github/workflows/install.yml` 中的 pip 安装命令及 `$required` 验证列表；
3. 更新 `dev/test_release_agent_imports.py` 增加导入冒烟测试；
4. 确保 CI 中的 `verify (win, x86_64)` 硬门禁覆盖该依赖。

---

## 14. 常见错误与应急排查速查

| 现象 | 根因 | 处置方式 |
| :--- | :--- | :--- |
| `std::regex` 报错崩溃 | OCR `expected` 含未转义正则符号 | 改用纯中文语义短语或双反斜杠转义，发版前必跑 `test_pipeline_regex.py` |
| `gh` 命令 404 / 没权限 | 未显式声明目标仓库 | 严格加上 `-R zhimaheiye/MaaHappyFish` |
| CI Release Job 跳过 | 仅 push 了分支，没有 push tag | 检查 `git push origin vX.Y.Z` |
| CI 选错监听任务 | `gh run list` 误抓了 branch push 任务 | 通过 `--json headBranch` 过滤 Tag 名确认 RUN_ID |
| Windows Runner verify 报错 | 缺少运行依赖或 `interface.json` 不一致 | 查看 verify job 详情，补齐 install.yml 或同步 interface.json |
