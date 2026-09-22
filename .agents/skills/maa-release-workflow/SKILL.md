---
name: maa-release-workflow
description: >-
  MaaHappyFish 项目版本发布、打包、打 Tag 及发布 CI 监控的调度技能入口。
  当用户要求“打包发新版”、“发 release”、“推 tag”、“升级版本号”、“打包并推送”时激活本技能。
---

# MaaHappyFish 发版调度入口 (Release Skill Entry)

本文件是 Antigravity 的薄调度入口（Thin Dispatch Entry）。为确保发版规范的单一事实源（Single Source of Truth），**所有发版逻辑、静态门禁、Git 规范及 CI 监控步骤一律以项目根目录下的唯一权威文档为准**。

> 📖 **唯一权威文档**：[`docs/release-workflow.md`](../../docs/release-workflow.md)

---

## 0. 执行前置准则（必须严格执行）

1. **先读权威正文**：
   在执行任何修改或命令前，**必须首先完整阅读并遵循 [`docs/release-workflow.md`](../../docs/release-workflow.md)**，严禁仅凭记忆或本入口描述执行操作。
2. **严格按文档执行**：
   发布流程包含 Step 0（Git 环境与分支安全核验）至 Step 10（里程碑边界），必须逐项跑通前置门禁，不得跳步。

---

## 1. Release 特有 Agent 安全规则（安全红线）

在执行发布任务时，Agent 必须严格遵守以下安全红线：

1. **未知修改立即停止**：
   修改前必须运行 `git status --short`。若工作区存在非本次发版所需、来源不明的修改或未跟踪文件，**必须立即终止发版流程并向用户汇报**，严禁私自暂存或清理。
2. **严禁覆盖或重建既有 Tag**：
   发版前必须校验目标 Tag 和对应 GitHub Release 在本地和远端均不存在。**绝对严禁删除、移动、覆盖或强制重建既有 Tag 与 Release**。
3. **严格限制分支与远端**：
   发版必须且只能在 `main` 分支上执行，且 `origin` 必须指向 `zhimaheiye/MaaHappyFish`。若存在分叉或需要非 fast-forward 推送，立即停止。
4. **禁止盲目暂存**：
   严禁将 `git add -A` 作为无脑操作。暂存后必须通过 `git status`、`git diff --cached --stat` 与 `git diff --cached` 仔细核查暂存区，确保仅包含本次发版所需变更。
5. **发布状态两阶段沉淀**：
   在 Tag 推送前，严禁提前将尚未构建发布的版本写入 `PROJECT_STATUS.md` 或 `docs/handoff/CURRENT.md`。只有当 GitHub Actions CI 全绿通过且 8 个构建目标资产核验完成后，才作为 post-release 确认提交记录。
6. **防范 CI Run 选错竞态**：
   推送 main 与推送 Tag 会触发两个相近的 CI Run，**严禁盲目抓取最新 Run**，必须通过过滤确认其对应的是目标 `vX.Y.Z` Tag ref，再执行 `gh run watch`。
