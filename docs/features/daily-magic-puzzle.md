# 每日魔幻拼图求解与执行

## 功能范围与入口

“每日魔幻拼图”是默认不勾选的 MFA 独立任务，不属于日常收尾，也不包含领奖流程。用户必须先停在拼图棋盘页；执行任何 Swipe 前仍需在 `[0,482,316,238]` 命中用户提供的 `拼图页面_识别.png`（阈值 `0.8`）。门禁失败安全停止。

当前支持三种规格：

| 规格 | 目标图片块 | Solver | 实机状态 |
| --- | --- | --- | --- |
| 4×4 棋盘 / 2×2 图片 | 4 块 | 原 multi-source BFS 最短路径 | 用户已验证页面门禁、求解与实际 Swipe 成功 |
| 5×5 棋盘 / 3×3 图片 | 9 块 | 有预算的 weighted A* | Candidate Ready，待用户首次实机验证 |
| 6×6 棋盘 / 4×4 图片 | 16 块 | pair-PDB 加强的有预算 weighted A* | Candidate Ready，待用户首次实机验证 |

MFA 的“拼图规格”默认选择 `4×4（2×2图片）`，因此旧用户行为不变。Select case 使用 Project Interface 原生子 option：4×4 只显示图片块 1~4，5×5 显示 1~9，6×6 显示 1~16。旧的 `每日魔幻拼图位置` 和 `每日魔幻拼图位置5x5` 配置键均保持不变。规格参数与位置参数必须由对应的最终 input option 在同一个 `custom_action_param` 中下发；MFA 对相同节点的多层参数对象采用后者整体覆盖，而不是深合并。

## 人工位置输入

图片块编号代表完整图片中的固定身份，不能按用户输入的位置重新排序：

```text
4×4 / 2×2 图片       5×5 / 3×3 图片       6×6 / 4×4 图片
1 2                   1 2 3                   
3 4                   4 5 6                   
                      7 8 9
                                              1  2  3  4
                                              5  6  7  8
                                              9 10 11 12
                                             13 14 15 16
```

每个输入均支持格号、`rNcN`、中文逗号和英文逗号，并兼容大小写与周围空格。例如 6×6 中：

```text
29 = r5c5 = R5 C5 = 5，5 = 5,5
```

`agent/puzzle_position.py` 先解析为 1-based `(row, col)`，再转换为 0-based 行优先索引。它验证必填图片块数量、范围和标准化后的重复位置；任何错误都在 Solver 与 Executor 启动前返回。

棋盘编号由 `build_puzzle_board_reference(board_size)` 动态生成：

```text
4×4                    5×5
    C1 C2 C3 C4            C1 C2 C3 C4 C5
R1   1  2  3  4        R1   1  2  3  4  5
R2   5  6  7  8        R2   6  7  8  9 10
R3   9 10 11 12        R3  11 12 13 14 15
R4  13 14 15 16        R4  16 17 18 19 20
                        R5  21 22 23 24 25
```

离线 4×4 点击预览工具仍可运行 `python tools/daily_magic_puzzle.py`；它不连接 MFA Controller，也未扩展为 5×5 UI。

## 状态、动作与 Goal

状态只保存有身份的目标图片块位置，灰色 filler 不编号：4×4 是 4 元组，5×5 是 9 元组，6×6 是 16 元组。

共用 `PuzzleMove(axis, index, shift)`：正数代表右/下，负数代表左/上。4×4 保持原 canonical shifts `-1 / +1 / +2`，共 24 个动作；5×5 使用 `-2 / -1 / +1 / +2`，共 40 个动作；6×6 使用 `-2 / -1 / +1 / +2 / +3`，共 60 个不重复动作，其中 `+3 == -3` 只保留一种。任意移动距离都只提交一次 Swipe。

两种规格都只接受棋盘内部、不跨边界的连续目标区域：

- 4×4：`1 2 / 3 4` 可落在 9 个连续 2×2 anchor；
- 5×5：`1 2 3 / 4 5 6 / 7 8 9` 可落在 9 个连续 3×3 anchor；
- 6×6：16 块按 4×4 row-major 排列，可落在 9 个连续 4×4 anchor；
- 任何越过棋盘右边界或下边界再回到第 1 列/行的环绕排列都不是 Goal。

## Solver

4×4 的 `PuzzleSolver` 和 43,680 状态 multi-source BFS 保持原路径，不用 5×5 泛化重写。

5×5 使用独立 `Puzzle5x5Solver`：

- state 只含 9 个目标块位置；
- 9 个合法 Goal anchor 同时进入 heuristic；
- heuristic 综合到各 anchor 的循环 Manhattan 距离与 12 条水平/垂直正确相邻关系；
- `best_cost` transposition table 去重；
- 连续同一行/列动作（包括 immediate inverse）不展开，因为可合并为单次 canonical shift；
- 默认预算为 300,000 expanded states 或 8 秒；
- 完整路径找到后才创建 `MaaPuzzleExecutor`；超预算会返回失败且不 Swipe。

第一版目标是稳定找到可执行解，不承诺 5×5 最少 Swipe。

6×6 复用同一有界搜索骨架，但不是只替换尺寸：

- state 只含 16 个目标块，不建立 36 格全排列；
- heuristic 组合 9 个 Goal anchor 的循环 Manhattan 距离，以及 24 条目标邻接边的精确双块 pattern database 距离；两张 PDB 各只有 `36P2 = 1260` 个状态；
- 保留 `best_cost` transposition table，并剪掉 immediate inverse 与所有可合并的连续同一行/列动作；
- 默认预算 400,000 expanded states 或 12 秒；只有得到完整解才交给 Executor；
- 固定 35 个 deterministic scramble（长度 2/3/5/8/10/15/20，每档 5 个）全部通过。20 步组 5/5，通过时间平均 0.470 秒、最慢 0.687 秒，最大 expanded 1040，最长解 65 步。

第一版 5×5/6×6 均以稳定可执行为目标，不承诺最少 Swipe。

## Geometry 与执行

`PuzzleGeometry` 保存棋盘尺寸、左上格 ROI 和右下格 ROI，以第一格中心到最后一格中心做线性插值，避免累计单格误差。

4×4 保持历史实机值：

```text
r1c1 ROI = [366,85,137,134]
r4c4 ROI = [781,499,137,134]
GRID_X = [435,573,712,850]
GRID_Y = [152,290,428,566]
BOARD_ROI = [366,85,552,548]
```

5×5 使用用户提供的真实 ROI：

```text
r1c1 ROI = [367,86,109,110]
r5c5 ROI = [806,525,109,109]
GRID_X = [422,532,642,751,861]
GRID_Y = [141,251,360,470,580]
BOARD_ROI = [367,86,548,548]
```

6×6 使用用户提供的真实 ROI，并按第一格中心到最后一格中心线性插值：

```text
r1c1 ROI = [365,82,91,91]
r6c6 ROI = [825,545,91,91]
GRID_X = [410,502,594,686,778,870]
GRID_Y = [127,220,312,405,497,590]
BOARD_ROI = [365,82,551,554]
```

正 shift 从左/上侧格心向右/下 Swipe，负 shift 从右/下侧格心向左/上 Swipe；±2 和 3 格都选择保证终点仍在棋盘内的起点。默认 Swipe 400ms、动作间隔 600ms，沿用已实机成功的 4×4 节奏，不改变旧规格速度。

## 代码级验证

运行 `python dev/test_daily_magic_puzzle.py`，验证：

- 原 4×4 全部 43,680 状态的最短距离、非跨界 Goal 和 24 个动作/坐标零回归；
- 5×5 的 9 个 Goal anchor、跨边界负样本、40 个动作及方向语义；
- 5×5 已完成、行、列、±2、行列混合基本场景；
- 固定种子、scramble length `1/2/3/5/8/10`、每档 5 个样本，共 30 个 deterministic case；
- 4×4/5×5 Geometry 端点、插值和 dry-run 坐标均位于棋盘范围；
- 1~25、`r5c5`、`5，5`、`5,5`、越界、缺块、重复位置；
- 搜索超预算时 Action 返回失败且 Fake Controller 零 Swipe；
- Interface 条件子 option、默认 4×4 与旧配置键兼容。
- MFA 多层 option 覆盖回归：最终 4×4/5×5 input payload 必须同时包含规格与全部位置；用户现场 5×5 状态 `13,11,21,15,19,2,22,6,4` 可在预算内求解。
- 6×6 的 9 个 Goal、跨边界负样本、60 个动作、±1/±2/3 方向、16 块 Parser、预算失败零 Swipe，以及六组实际 dry-run 坐标均在棋盘内；
- 6×6 deterministic benchmark 35/35，包含 10/15/20 步深乱序；20 步组统计见上文。

本轮严格使用用户提供的 ROI 做代码适配，未启动 MFA、模拟器或真实拼图；6×6 状态为 Candidate Ready，等待用户自行填写 16 块位置完成首次实机验证。
