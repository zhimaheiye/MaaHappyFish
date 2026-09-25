# 全局步骤可恢复启动与导航审查

**文档状态：长期维护入口。** 本文保存跨任务的步骤可恢复导航契约与审查结果。它不替代各功能文档中的完整状态机；每个任务的具体 ROI、模板、动作和业务分支仍以对应 `docs/features/*.md` 为准。

## 通用契约

对适合步骤恢复的普通自动化任务，启动顺序统一为：

```text
当前真实 UI
→ Deepest-First 识别最深已知阶段
→ 复用该阶段之后的既有流程
→ 每次动作后获取 fresh screenshot 验证
→ 未知状态安全 Abort
```

- 已在流程中间时，不重复点击入口、不强制回主鱼缸，也不重复执行已经完成的不可逆动作。
- 结果弹窗、局内状态和二级页面优先于功能主页、入口面板和主鱼缸等较浅门禁。
- 恢复启动不能放宽购买、兑换、删除、邀请、免费次数、每日体力或付费按钮的既有门禁。
- 缺少身份上下文时，只有存在经过证据确认的安全回退路径才允许返回父页面重新扫描；否则将该状态登记为 `Intentional Unsupported` 并停止。
- 缺少截图、模板或可靠 OCR 时登记为 `Live Blocked / Missing Evidence`，不得用固定坐标或负向推断补洞。

## 新增与修改任务检查表

每个新增独立任务，以及每次扩展 `StartRouter` / `ResumeRouter` 时，交付前必须完成：

1. 在对应功能文档中列出所有合理启动状态及恢复后继。
2. 按最深到最浅排列候选，确认宽泛主页门禁不会吞掉结果态或局内态。
3. 标明需要 runtime context 的状态；上下文丢失时记录安全回退或故意不支持原因。
4. 记录标准入口、每个新增恢复入口、未知状态、不可逆动作防重复和任务取消边界的代码级验证状态。
5. 将该任务加入下方矩阵；功能状态变化时同步更新 `CURRENT.md` 与 `PROJECT_STATUS.md`。

## 审查矩阵

本表“支持”表示当前代码存在对应状态门禁和恢复后继；本轮新增项只完成离线代码级验证，未因此升级为 MFA/模拟器实测通过。

| Task | 合理启动状态 | 当前支持 | Resume entry | 需要 runtime context | 安全支持边界 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| `StartAppTask` | 启动页、公告/全局弹窗、已进主鱼缸 | 支持 | `CloseAnnouncement` / `ClickEnterGame` / `ConfirmMainScreen` | 否 | 只点已识别入口 | 已支持 |
| `OpenShellTask` | 主鱼缸、分类页、待开始页、打开贝壳、继续、随机奖品、完成结果 | 全部接入 | `OpenShellStartRouter` | 循环次数由现有 Reco 维护 | 半轮只计一次；未知页 StopTask | 本轮补齐 |
| `GemGiftBoxTask` | 主鱼缸、宝藏页、兑换页 | 支持已知页面 | 入口节点并列路由 | 配方选择 | 消耗确认弹窗缺上下文时停止 | 已支持；确认弹窗故意不支持 |
| `GemOrderTask` | 主鱼缸、订单页 | 支持 | `GemOrderTask` / `GemOrderRouter` | 删除目标与循环状态 | 删除确认弹窗单独启动不处理 | 已支持；删除确认故意不支持 |
| `FriendGemTask` | 主鱼缸、好友列表、海牛好友缸、普通好友缸 | 支持 | `FriendGemStartRouter` | 当前好友/访问状态由画面重建 | 未知好友页停止 | 已支持 |
| `ManateeTask` | 好友列表、海牛页面 | 支持 | `ManateeStartRouter` | 好友访问状态 | 未知页停止 | 已支持 |
| `WishingLampTask` | 主鱼缸、神灯活动页、循环结果页 | 支持既有循环状态 | `WishingLampStartRouter` | 当轮结果 | 只点正向门禁 | 已支持 |
| `GreenWildTask` | 主鱼缸、活动页、任务/奖励页 | 支持 | `GreenWildStartRouter` | 日常子流程由 DailyRoutine 管理 | 未知页跳过并返回调度 | 已支持 |
| `PrincessTask` | 主鱼缸、普通页、宝箱任务页、成功/失败结果弹窗 | 支持 | `PrincessStartRouter` | 否 | 积分不足文字不直接推断关闭位置 | 本轮补齐 |
| `CollectFishTask` | 鱼缸 1/2/3、选择器、单/双缸初始化及收宝循环 | 支持 | `CollectFishStartRouter` | 单调缸位、双缸时间锚 | 当前画面优先并重新校准 | 已支持 |
| `PatrolTask` | 鱼缸 1/2/3、选择器、管理页、海星页 | 支持 | `PatrolStartRouter` | 巡检槽位/喂食上下文 | 通用选择喂食弹窗故意 Abort | 已支持；弹窗故意不支持 |
| `FeedStarfishStandalone` | 鱼缸 1/2/3、管理页、海星页 | 支持 | `FeedStarfishStandaloneStartRouter` | 选择喂食需海星身份 | 只有编号鱼缸可点管理；选择喂食弹窗停止 | 本轮补齐；弹窗故意不支持 |
| `BuyFishFoodTask` | 主鱼缸、喂食弹窗、商店列表、商品详情 | 支持 | `BuyFishFoodStartRouter` | 购买袋数 | 每批重新验证详情/商店页 | 已支持 |
| `FishingTask` | 主鱼缸、活动网格、地点页、选饵、等待咬钩、结算、购买提示 | 支持 | `FishingStartRouter` | 杆数、饵食模式 | 只点实际命中退出/饵食目标 | 已支持 |
| `SeaOtterGemTask` | 好友列表、好友鱼缸 | 支持两类约定起点 | `SeaOtterStartRouter` | 当前好友和体力扫描 | 主鱼缸及其它页面不自动导航 | Intentional Unsupported：仅好友列表/好友缸 |
| `BandFishTask` | 主鱼缸、游乐园、我的演出、选曲、演出、结算 | 除好友邀请弹窗外支持 | `BandFishStartRouter` | 好友邀请需要 `target_slot/name` | 选曲保留黄色选中门禁；邀请弹窗停止 | 本轮补齐；邀请弹窗故意不支持 |
| `SeaDiveTask` | 鱼缸 1/2/3、选择器、主页、深度选择、局内、结算、挽留 | 支持 | `SeaDiveStartRouter` | 否；每轮回主页重判 FREE/PAID | 只选 100 米、只点免费、绝不点继续下潜/x12 | 本轮补齐 |
| `FishBabyTask` | 主鱼缸、鱼宝主页、孵化大类、三类子项、选宝宝层 | 支持 | `FishBabyStartRouter` | 本轮偏好与编号映射 | 未知工具栏/编号冲突停止 | 已支持；新三列配置待用户运行 |
| `DailyRoutineTask` | 任意可由首个子任务识别的安全页面 | 调度器本身可恢复队列；UI 恢复由子任务负责 | `DailyRoutineDispatcher` | 必须：队列与 active 状态 | 不跨子任务猜页面 | 容器支持；逐项以本表为准 |
| `GoldenDolphinTask` | 主鱼缸、游乐园、确认弹窗、隐藏启动/奖励雨、结算 | 支持 | `GoldenDolphinNavigationAction` | 奖励优先级、局数 | 局内须命中奖励/启动贝币；结算计数一次 | 本轮补齐 |
| `DailyMagicPuzzleTask` | 拼图页面 | 仅支持该页 | `DailyMagicPuzzleSolve` | 6×6 当前盘面 | 非拼图页不导航 | Intentional Unsupported：只允许拼图页 |
| `ShakeGameTask` | 主鱼缸、游乐园、确认弹窗、局内、结算 | 结算及浅层支持；局内缺证据 | `ShakeGameNavigationAction` | MuMu 路径与明确 VM index | 结算模板命中才退出；绝不默认 VM 0 | Live Blocked：局内缺截图/模板 |
| `ShakeGemCollectTestTask` | 指定主鱼缸测试场景 | 仅固定测试入口 | `ShakeGemCollectVerifyTank` | 明确 VM index | 不扩展为通用任务 | Intentional Unsupported：测试专用 |
| `GoldShellCouponTask` | 主鱼缸、分类页、金贝壳页、兑换后确认/结果 | 支持 | `GoldShellCouponRouter` | 当轮兑换确认 | 海星误入可返回；未知页停止 | 已支持 |
| `EmulatorAdTask` | 主鱼缸、广告中、广告后 | 支持既有路由 | `EmulatorAdRouter` | 广告轮次/启动标记 | 只在适配模拟器路径运行 | 已支持 |
| `MobileAdTask` | 主鱼缸、广告页、返回后页面 | 支持既有路由 | `MobileAdRouter` | 周期与设备分辨率 | 仅 ADB 真机约定；MuMu 不支持 | 已支持其既定设备边界 |

## 维护规则

- 全仓导航审查任务应逐项补充矩阵，不能用“全部支持”概括尚未核对的任务。
- 各行必须区分代码实现、离线验证和 MFA 实测；单个任务通过不代表全仓通过。
- 用户纠正、当前代码与最新日志优先于旧审查结论；结论变化时直接更新本表当前状态。
- 这是通用能力的长期入口。以后新增功能不得只实现主鱼缸入口后结束，必须在设计阶段完成本检查表，或明确说明为何该任务只允许特定页面启动。
