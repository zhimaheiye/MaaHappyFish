---
name: maa-log-repair-workflow
description: Pull MaaHappyFish and its happyfishagent evidence repository, inspect new MFA/MaaFramework automation error logs, implement evidence-backed fixes, close project documentation, remove only the analyzed temporary evidence, and push both repositories safely. Use when the user asks to analyze or repair MaaHappyFish automation logs, process new happyfishagent evidence packages, or repeat the full error-log maintenance workflow.
---

# MaaHappyFish Log Repair Workflow

Treat a request such as “分析并修复错误日志” as authorization for this full workflow unless the user narrows its scope: synchronize both repositories, analyze new evidence, repair current project bugs, run code-level validation, close documentation, delete the analyzed temporary evidence, commit, push, and verify the remotes.

## Establish context and preserve user work

1. Work in `D:\happyfishgame`; use `D:\happyfishagent` only as the evidence repository.
2. Read `AGENTS.md`, `PRODUCT.md`, `docs/handoff/CURRENT.md`, `docs/handoff/DEVELOPMENT_PLAYBOOK.md`, and the affected feature documents before editing.
3. Inspect `git status --short`, branch, upstream, remotes, and ahead/behind in both repositories. Treat all existing modifications and untracked files as user work. Never reset, stash, clean, or stage them without explicit scope.
4. Fetch first, inspect incoming names, then use only a fast-forward pull. If local tracked changes overlap incoming changes, stop and report the conflict instead of overwriting them.

## Analyze evidence before changing code

1. Identify newly pulled packages under `D:\happyfishagent\mfa-evidence`. Extract only the packages in this run to a uniquely named temporary directory inside that repository.
2. Read each manifest, summary, report, and the raw GUI/MaaFramework/Agent log window around its timestamp. A watchdog label such as `ERROR`, `ENV_DOWN`, or `STOPPED_WITH_ABORT` is a lead, not a root cause.
3. Compare the package version and timestamp with the current code. Classify every package as one of:
   - a current, evidence-backed business bug;
   - an older-version issue already fixed by later code or later successful logs;
   - an environment or deliberate operator state;
   - an upstream/native-client issue outside this repository.
4. Do not turn log coordinates into blind clicks, infer success from `StopTask`, or patch around unknown screens. Unknown states must stop safely.

## Repair the smallest proven defect

- Change only current defects supported by code plus logs. Preserve existing task contracts and resource-safety gates.
- When a defect belongs to prebuilt MFAAvalonia or another unavailable upstream component, do not create a Python/Pipeline workaround that claims to fix it. Record the exact boundary in `ISSUES.md` and the relevant feature document.
- Add or tighten targeted regression assertions when they protect the observed contract. For Pipeline edits, preserve valid Maa regex and Agent registration references.
- Follow the bug documentation closure rules in `AGENTS.md`: update `ISSUES.md`, `PROJECT_STATUS.md`, `docs/handoff/CURRENT.md`, and affected feature documents. Distinguish code implementation, code-level validation, MFA/device evidence, and live-blocked work.

## Validate without consuming live resources

Run the smallest affected specialized tests, then the applicable repository gates:

```text
python dev/test_pipeline_regex.py
python dev/test_agent_registration_refs.py
python dev/test_release_agent_imports.py
python -m py_compile <changed Python modules>
git diff --check
```

Add `dev/test_update_contract.py` when interface/update files change. Do not run MFA, MuMu, ADB, browser, or other UI tests unless the user explicitly asks. Report baseline failures separately from failures caused by changed paths.

## Clean evidence and publish safely

1. Delete evidence only after the repair and code-level validation succeed. Remove exactly the packages analyzed in this run and the unique extraction directory. Preserve long-term fixtures, unrelated packages, and every pre-existing untracked file.
2. Recheck both worktrees. Stage exact authorized paths only; commit the project fix and evidence deletions in their respective repositories.
3. Fetch again immediately before pushing. If either remote advanced, reconcile visibly and without force-push. Push each repository's configured main branch to `origin`.
4. Fetch once more and verify local `HEAD` equals `origin/main`. Report both commit IDs, validation commands/results, deleted evidence paths, preserved user files, remaining upstream/environment issues, and the fact that live MFA/device testing was not performed.
