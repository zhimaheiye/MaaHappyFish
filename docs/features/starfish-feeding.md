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

## 坑点记录 (Pitfalls)
1. **Pipeline 节点超时重置**
   - **现象**: 喂食定时器死活不触发。
   - **修复**: 废弃 Pipeline 内部 timeout 定时，全量迁移到 Python 侧计算时间差。
2. **深层返回路径崩溃**
   - **现象**: 喂食完毕退出到主界面的 `StarfishReturnSecond` 配置了 3000ms 超时，未识别到气泡直接导致任务失败。
   - **修复**: 在其后接上 `ResumeHarvest` (timeout:-1) 作为缓冲安全垫，保障容错。

## 当前状态
- **状态**: 生产就绪，稳定运行。
- **关键文件**: `agent/my_reco.py` (`CheckStarfishTimerReco`), `assets/resource/pipeline/collect_fish.json`
