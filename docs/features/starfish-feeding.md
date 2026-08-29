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
VerifyTankSettings (OCR 校验已进入鱼缸设置页)
  ↓
SelectCuteStarfish (固定点击萌海星卡片)
  ↓
VerifyStarfishPanel (OCR 校验已打开萌海星面板)
  ↓
ClickReplenishFood (OCR 识别 "补充")
  ↓
ClickFishFoodBag (TemplateMatch 普通鱼食袋.png, 固定点击第一格鱼食)
  ↓
CheckFoodFull (TemplateMatch 鱼食已装满.png 校验进度条右侧填满)
  ├── 校验成功 → 播报 "鱼食补充成功！进度条已加满"
  └── 校验失败 → 播报 "提示：未检测到鱼食加满，请检查背包"
  ↓
StarfishReturnFirst (返回1)
  ↓
StarfishReturnSecond (返回2)
  ↓
ResumeHarvest (万能返回节点)
```

## 防误触机制

- **背景**: 游戏内频繁点击水域会触发鱼的详细信息横幅，遮挡主要 UI。
- **设计**: 不使用随机点击水域来取消焦点，使用 `DismissFishBannerIfOpen` 挂机 `4.5s` (idle)，等待横幅自然超时消失。

## 迭代与 Debug 因果日志

### 2026-08-29 · 修复海星入口坐标过时与全屏 OCR 不稳定

- **现象**: 日志显示已触发定时喂食，但实机未真正补充鱼食，或打开页面后很快返回鱼缸。
- **根因**: 设置按钮仍使用旧坐标 `[110, 30, 50, 50]`；选择萌海星依赖全屏 OCR，易受游鱼、场景和其他文字干扰；链路缺少设置页与海星面板的显式确认。
- **修复**:
    1. 设置入口改为实机确认坐标 `[176, 54, 4, 4]`，萌海星卡片改为固定区域 `[450, 255, 100, 160]`；
    2. 新增 `VerifyTankSettings` 和 `VerifyStarfishPanel`，分别在限定 ROI 内确认「鱼缸」和「萌海星」；
    3. 「补充」OCR 限定到 `[900, 270, 260, 90]`，各关键页面切换延时提升至 `2200ms`；
    4. 入口校验失败时只播报一次并安全返回，不进入递归重试；主链路与独立单次喂食链路同步更新。
- **保留保护**: 继续保留触发播报以及 `DismissFishBannerIfOpen` 的 4.5 秒防横幅等待。
- **来源**: 根据台式机实机修复记录选择性移植，未整文件覆盖。

### 2026-08-29 · 修复点击蓝色加号打开商店导致海星未喂食

- **现象**: 日志显示触发补充并命中加号，但海星存粮没有增加；实机复现时还会进入糖果/鱼食购买页。
- **根因**: 实机截图取证确认，「选择喂食」弹窗左上角的蓝色加号是“购买鱼食”入口，不是投喂按钮。旧链路一直精准点击了错误入口。另外 `ClickAddFoodTarget.next` 同时包含 `CheckFoodFull` 和 `StarfishReturnFirst`，校验一失败就会在同一层候选里立即切换到返回，导致投喂动画未完成就退出。
- **修复**:
    1. 新增 `普通鱼食袋.png`，将主干与单次喂食链路改为点击第一格普通鱼食，并显式指定 `(679, 215)` 作为点击中心；
    2. 游戏规则确认：购买时一袋鱼食为 30 粒，但投喂海星时点击一次鱼食袋会一次性加满，或放入当前可用的全部鱼食，因此无需循环点击；
    3. `CheckFoodFull` 的 ROI 限定为海星主面板进度条右端 `[640, 265, 260, 90]`，避免喂食弹窗遮挡区域造成误判；本地实测主面板命中 `1.0`，弹窗遮挡时仅 `0.229`；
    4. 点击鱼食后等待 `2800ms`，校验超时提升到 `6000ms`；`next` 只保留校验节点，识别失败才进入一次失败播报和安全返回；
    5. 修复 `CalcFishingFoodAction` 中 `extra_mins` 在“存粮充足”分支可能未定义的问题。
- **回归**: JSON 解析、Python 编译、仓库内 MaaFramework 资源加载、鱼食袋/满仓模板匹配均通过。蓝色加号模板已从海星链路移除，消除误开商店风险。

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

### 2026-08-28 · 修复加号硬编码坐标偏差，增加「鱼食已装满」进度条回执校验

- **现象**: 连续两轮喂食日志显示准备投喂，但海星存粮未加满。
- **根因**: `ClickAddFoodTarget` 写死了固定坐标 `target: [646, 179, 64, 78]`，导致模板匹配到加号后并未点击加号实际所在位置；且缺乏喂食后的状态确认。
- **修复**:
    1. 移除 `ClickAddFoodTarget` 的写死 target，改为自动命中加号中心点击；
    2. 引入 `CheckFoodFull` 节点，通过 `TemplateMatch` 匹配 `鱼食已装满.png`（橙色进度条右侧圆弧饱满状态），成功装满即在 UI 日志面板输出 `[海星喂食] 鱼食补充成功！进度条已加满，海星存粮充沛！`；若未满则触发 `NotifyFoodNotFull` 提示检查背包。
- **回归**: 形成【点击加号 → 视觉校验装满 → 状态回执播报 → 安全返回】的完整闭环。

## 当前状态

- **状态**: 生产就绪，具备进度条回执校验闭环。
- **关键文件**:
    - `agent/my_reco.py` (`CheckStarfishTimerReco`)
    - `assets/resource/pipeline/collect_fish.json` (`ClickFishFoodBag` -> `CheckFoodFull`)
    - `assets/resource/image/鱼食已装满.png`
    - `assets/resource/image/普通鱼食袋.png`
