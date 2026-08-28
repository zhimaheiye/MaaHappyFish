# 功能档案：海星定时喂食 (starfish-feeding.md)

## 功能概述与触发机制
自动打开设置面板，找到海星并补充鱼食。为解决 MFA 原生节点超时在循环任务中被重置的问题，触发器改用 Python 侧计时。
- **触发器**: `CheckStarfishTimerReco` (自定义识别器，基于 `time.time()`)
- **周期**: 由 UI 选项提供（如 30秒测试/1分/30分/不喂食）。

## 执行流程 (Workflow)
```text
TriggerStarfishFeed 
  ↓
OpenSettingsForStarfish
  ↓
DismissFishBannerIfOpen (4500ms post_delay 等待 UI 自然恢复)
  ↓
ClickSettingsIcon
  ↓
SelectCuteStarfish (OCR 识别 "萌海星|萌")
  ↓
ClickReplenishFood (OCR 识别 "补充")
  ↓
ClickAddFoodTarget (TemplateMatch 海星_加号.png)
  ↓
StarfishReturnFirst
  ↓
StarfishReturnSecond
  ↓
ResumeHarvest (万能返回节点)
```

## 防误触机制
- **背景**: 游戏内频繁点击水域会触发鱼的详细信息横幅，遮挡主要 UI。
- **设计**: 不使用随机点击水域来取消焦点，使用 `DismissFishBannerIfOpen` 挂机 `4.5s` (idle)，等待横幅自然超时消失。

## 迭代与 Debug 因果日志

### 2026-08-28 · 海星喂食 on_error 死循环狂点左上角导致游戏退出
- **现象**: 挂机运行一段时间后游戏异常退出回到模拟器桌面，MFA 仍在运行但反复报错。日志分析显示 20:17~21:26 期间产生了 21,000+ 次对左上角 `[110, 30, 50, 50]` 的密集点击。
- **根因**: `ClickSettingsIcon` 和 `SelectCuteStarfish` 的 `on_error` 指向了 `OpenSettingsForStarfish`，一旦某次 OCR 识别「萌海星」失败，会引发死循环无限重试点击左上角，高频事件堆积或点到系统退出区域导致游戏崩溃/退至桌面。
- **修复**: 
  1. 彻底切断喂食流程内部的错误递归，`ClickSettingsIcon.on_error` 和 `OpenSettingsForStarfish.on_error` 一律熔断退出至 `ResumeHarvest`；
  2. `SelectCuteStarfish.on_error` 及后续节点失败时仅执行一次 `StarfishReturnFirst` 退出设置弹窗后回归主干；
  3. 主干 `ResumeHarvest` 调度链加入 `HandleCloseAnnouncement` 与 `HandleEnterGame` 自动恢复。
- **回归**: 验证任一节点识别失败均安全熔断返回 `ResumeHarvest`，不再产生高频连击。

### 2026-08-28 · 海星喂食动作节奏全链路延时与稳定性加固
- **现象**: 实机运行时，进入海星页面后偶尔在加号尚未完全淡入展开时过快触发了左上角「返回」，导致喂食未完成就退出。
- **根因**: 原配置中 `ClickReplenishFood` 仅等待 800ms，加号动画未完全加载；`ClickAddFoodTarget` 超时较短（5s）且点击后仅等待 600ms，动画未播完即连续快速点击两层返回退出，动作节奏过急。
- **修复**: 
  1. `ClickReplenishFood` 的 `post_delay` 提升至 `1800ms`，确保加号充能弹窗充分展开；
  2. `ClickAddFoodTarget` 的 `timeout` 提升至 `8000ms`，阈值放宽至 `0.7`，点击后 `post_delay` 提升至 `2000ms`，给足加粮充能动画播放时间；
  3. `StarfishReturnFirst` / `StarfishReturnSecond` 返回动作间隔分别提升至 `1500ms` 与 `2000ms`，确保界面彻底平稳再回归主干收宝。
- **回归**: 实机全流程动作平稳从容，每个步骤均等动画彻底完成再进行下一步。

## 当前状态
- **状态**: 生产就绪，动作延时已加固。
- **关键文件**: `agent/my_reco.py` (`CheckStarfishTimerReco`), `assets/resource/pipeline/collect_fish.json`


