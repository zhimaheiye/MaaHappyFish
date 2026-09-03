# 钓鱼达人功能设计与状态机规范 (FishingTask)

## 1. 业务目标与启动契约 (Start Contract)

- **功能概述**：自动从自身水族箱主界面（或任意中途阶段）进入游乐园，开启钓鱼达人活动并前往指定钓鱼地点。
- **步骤可恢复启动契约（Step-resumable Start Contract）**：
  任务具备自适应中途启动恢复能力，支持从以下 4 个已知阶段中的任意一个阶段直接启动或重启：
  1. **钓鱼场景（未甩杆）**：直接识别「甩杆」按钮（`FishingStartAtScene`），判定任务已就绪并优雅完成，不发生额外跳转，0 鱼饵消耗；
  2. **钓鱼地点选择大地图**：直接识别「钓鱼达人」标题（`FishingStartAtLocationMap`），直接选取配置地点进入，无需倒退回主界面；
  3. **2×6 游乐园活动弹窗**：直接识别第一排第二格钓鱼达人图标（`FishingStartAtActivityGrid`），点击进入大地图并选点；
  4. **自身水族箱主界面**：识别公主任务标志（`FishingStartAtOwnTank`），点击游乐园摩天轮入口，完整执行全流程。
- **阶段红线约束（Phase 1）**：
  - **严禁点击甩杆**；
  - **严禁消耗任何鱼饵**；
  - 到达未甩杆静止钓鱼场景（`FishingSceneReady`）即优雅停止。

---

## 2. 状态机流程图

```text
FishingTask (入口)
    ↓
FishingStartRouter (最深已知阶段优先路由)
    ├─ 1. [最深] 已在钓鱼场景 ──> FishingStartAtScene (OCR "甩杆") ───> FishingSceneReady (完成)
    ├─ 2. 已在地点选择大地图 ──> FishingStartAtLocationMap (OCR "钓鱼达人") ──> FishingLocationRouter ──┐
    ├─ 3. 已打开 2x6 活动面板 ──> FishingStartAtActivityGrid (模板匹配鱼竿) ──> FishingNavActivityGrid ─┤
    └─ 4. [最浅] 还在自身水族箱 ──> FishingStartAtOwnTank (模板匹配主界面) ────> FishingNavOpenAmusement ┘
                                                                                      │
                                                                                      ▼
                                                                            FishingLocationRouter
                                                                         (根据选项 DirectHit 点击地点)
                                                                            ├─ 星河 (566, 109)
                                                                            ├─ 冰川 (315, 251)
                                                                            ├─ 宫殿温泉 (905, 67)
                                                                            ├─ 魔法塔楼 (848, 262)
                                                                            ├─ 大戏台 (443, 461)
                                                                            └─ 星空湖 (1143, 454)
                                                                                      │
                                                                                      ▼
                                                                            FishingSceneReady
                                                          (OCR 校验「甩杆」，DoNothing 优雅停止)
```

---

## 3. 地点配置与选项映射

通过 `assets/interface.json` 中的 `钓鱼地点` 单选配置，利用 `pipeline_override` 将 `FishingLocationRouter.next` 重定向至对应地点的选择节点。各地点在大地图上的相对布局固定，节点采用 `DirectHit` 定位点击并由 `FishingSceneReady` 严格闭环校验，避免艺术字 OCR 识别分词或字符杂质（如 `宫m殿温泉`）：

| 地点名称 | 解锁状态 | 识别方式 | 点击 Target 坐标 | 场景校验 |
| :--- | :--- | :--- | :--- | :--- |
| **星河** | 已解锁 | `DirectHit` | `[566, 109, 30, 20]` | OCR 验证 `甩杆` |
| **冰川** | 已解锁 | `DirectHit` | `[315, 251, 30, 20]` | OCR 验证 `甩杆` |
| **宫殿温泉** | 已解锁 | `DirectHit` | `[905, 67, 30, 20]` | OCR 验证 `甩杆` |
| **魔法塔楼** | 已解锁 | `DirectHit` | `[848, 262, 30, 20]` | OCR 验证 `甩杆` |
| **大戏台** | 已解锁 | `DirectHit` | `[443, 461, 30, 20]` | OCR 验证 `甩杆` |
| **星空湖** | 已解锁 | `DirectHit` | `[1143, 454, 30, 20]` | OCR 验证 `甩杆` |

---

## 4. 场景就绪判定 (`FishingSceneReady`)

进入任意钓鱼场景后，右下角必定出现绿色圆形“甩杆”按钮，左下角出现“选择鱼饵”，顶部出现地点名称与“查看鱼”。
- **识别条件**：`recognition`: `OCR`, `expected`: `甩杆`, `roi`: `[1050, 520, 160, 100]`
- **动作**：`DoNothing`（无后续节点，任务正常结束退出）

---

## 5. Phase 2 自动钓鱼攻坚规划（储备）

1. **甩杆到咬钩延迟**：实测各水域咬钩等待时长约在 2~6 秒；
2. **高速捕获机制**：红色感叹号出现时间仅 300~600ms，需高频轮询局部浮漂 ROI 或监听右下角按钮文本由「甩杆」变为「收杆」；
3. **样本保护原则**：在鱼饵充足且开启全量录屏/高速抽帧时方可启动 Phase 2 测试。