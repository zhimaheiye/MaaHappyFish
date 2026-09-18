# -*- coding: utf-8 -*-
"""开贝壳完成后的退出状态机语义回归测试。

背景（2026-09-18 实机取证，client_avalonia/debug/on_error/2026.09.18-20.29.01.662_OpenShellDone.png）：
- 大章鱼开贝壳页点击一次左上角“返回”只会退到贝壳分类页，不是主鱼缸；
- 该失败帧离线匹配：开贝壳_误触识别.png = 1.0000 HIT，主界面特征.png = 0.357 MISS，
  开贝壳_识别.png = 0.3631 MISS。

本测试用页面级识别语义驱动真实 Pipeline 图（assets/resource/pipeline/features/open_shell.json），
模拟 MaaFramework 的 next 列表语义（候选按序、首个命中生效、全部未命中走 on_error），
覆盖退出状态机的四个业务场景：
  Case 1 真实两级返回（第一次返回 -> 分类页 -> 第二次返回 -> 主鱼缸）
  Case 2 一次返回直达主鱼缸（不产生多余点击）
  Case 3 GreenWildDaily 上下文（返回后继续 GreenWildDailyBuyFishEntry）
  Case 4 独立 OpenShellTask（残留 pending 标记也不得劫持，走 OpenShellStandaloneComplete）

并覆盖入口重试状态机（点击入口后仍在主鱼缸 -> 重新识别入口 -> 重试，直到进入贝壳分类页）：
  E1 第一次点击即成功（不进入重试）
  E2 第一次被游鱼挡住、第二次成功（每次重试使用重新识别的最新 bbox）
  E3 连续多次被挡后成功（不提前 Abort）
  E4 永远被挡（宽松上限 15 次后安全熔断，不无限循环）
  E5 点击后落在未知页面（不再盲点入口，保持安全失败）
  E6 重试计数按 task_id 隔离（新任务运行自动归零）
"""
import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
OPEN_SHELL_PATH = ROOT / "assets/resource/pipeline/features/open_shell.json"
GREEN_WILD_PATH = ROOT / "assets/resource/pipeline/features/green_wild.json"

GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]

MAIN_TANK = "main"
CATEGORY_PAGE = "category"
OCTOPUS_PAGE = "octopus"

# 各退出链节点的识别语义：其 recognition 在哪些页面能命中。
# 依据 2026-09-18 失败帧离线匹配与同一次实机运行的节点级证据：
# - OpenShellVerifyMainAfterDone（主界面特征.png）只命中主鱼缸（分类页实测 0.357 MISS）；
# - OpenShellReturnFromCategory（OCR “返回” roi [0,0,189,146]）：分类页与大章鱼页左上角
#   都有同款“返回”（OpenShellDone 在大章鱼页命中 [50,32,53,29]；分类页见失败帧与
#   兑换金贝壳券实机两级返回），因此两页均可命中；
# - DirectHit 节点（OpenShellStandaloneComplete / OpenShellAbort）恒命中。
RECO_PAGES = {
    "OpenShellVerifyMainAfterDone": {MAIN_TANK},
    "OpenShellReturnFromCategory": {CATEGORY_PAGE, OCTOPUS_PAGE},
}

# 退出链的终止节点：到达即停止下钻（后续业务链不属于退出状态机）。
TERMINAL_OUTCOMES = {
    "OpenShellStandaloneComplete": "standalone_complete",
    "OpenShellAbort": "abort_stop_task",
    "GreenWildDailyOpenShop": "green_wild_buy_fish",
}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


class MockTaskDetail:
    def __init__(self, task_id):
        self.task_id = task_id


class MockArg:
    def __init__(self, param=None, task_id=200000001):
        self.custom_action_param = json.dumps(param or {})
        self.custom_recognition_param = self.custom_action_param
        self.task_detail = MockTaskDetail(task_id)


class MockContext:
    def override_pipeline(self, data):
        self.override = data


class OpenShellExitSimulator:
    """按 Maa next 列表语义驱动真实 open_shell.json 退出链。"""

    def __init__(self, pipeline, buy_fish_reco):
        self.pipeline = pipeline
        self.buy_fish_reco = buy_fish_reco
        self.page = None
        self.visited = []        # 识别命中并执行的节点（按序）
        self.missed = []         # 在 next 列表中被评估但未命中的候选
        self.clicks = []         # 退出链中实际执行的 Click
        self.outcome = None

    def reco_hit(self, node_name):
        if node_name in RECO_PAGES:
            return self.page in RECO_PAGES[node_name]
        if node_name == "GreenWildDailyBuyFishEntry":
            # 委托真实 CustomRecognition 判定（daily_routine_state / green_wild_daily_state）
            return self.buy_fish_reco.analyze(MockContext(), MockArg()) is not None
        if node_name in TERMINAL_OUTCOMES:
            return True  # DirectHit
        raise AssertionError(f"退出链意外到达节点: {node_name}")

    def _apply_action(self, node_name):
        node = self.pipeline[node_name]
        if node.get("action") == "Click":
            self.clicks.append(node_name)
            if node_name == "OpenShellReturnFromCategory":
                # 真实页面栈：大章鱼页 --返回--> 分类页 --返回--> 主鱼缸
                self.page = MAIN_TANK if self.page == CATEGORY_PAGE else CATEGORY_PAGE
        elif node.get("action") == "StopTask":
            self.outcome = TERMINAL_OUTCOMES[node_name]
            return False
        return True

    def _follow(self, node_name):
        self.visited.append(node_name)
        if node_name in TERMINAL_OUTCOMES:
            self.outcome = TERMINAL_OUTCOMES[node_name]
            return
        if not self._apply_action(node_name):
            return
        for cand in business_next(self.pipeline[node_name]):
            if self.reco_hit(cand):
                self._follow(cand)
                return
            self.missed.append(cand)
        for cand in self.pipeline[node_name].get("on_error", []):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        raise AssertionError(f"{node_name} 的 next 与 on_error 均未命中，退出链悬空")

    def run_exit_after_done(self, page_after_first_click):
        """OpenShellDone 已点击第一次返回，从其 next 列表开始解析。"""
        self.page = page_after_first_click
        for cand in business_next(self.pipeline["OpenShellDone"]):
            if self.reco_hit(cand):
                self._follow(cand)
                return self
            self.missed.append(cand)
        for cand in self.pipeline["OpenShellDone"].get("on_error", []):
            if self.reco_hit(cand):
                self._follow(cand)
                return self
        raise AssertionError("OpenShellDone 退出链悬空")


def setup_standalone_context():
    from agent.runtime_state import daily_routine_state, green_wild_daily_state

    daily_routine_state["active"] = False
    daily_routine_state["step"] = ""
    green_wild_daily_state["pending_buy_fish"] = False


def run_tests():
    # Maa 将多份 pipeline JSON 合并进同一资源池，退出链会跨 open_shell.json 与
    # green_wild.json（GreenWildDailyBuyFishEntry 在后者），这里同样合并驱动。
    pipeline = json.loads(OPEN_SHELL_PATH.read_text(encoding="utf-8"))
    pipeline.update(json.loads(GREEN_WILD_PATH.read_text(encoding="utf-8")))

    # 静态契约：OpenShellDone 第一次返回后的候选顺序（主鱼缸优先，分类页兜底）
    assert business_next(pipeline["OpenShellDone"]) == [
        "OpenShellVerifyMainAfterDone",
        "OpenShellReturnFromCategory",
    ]
    assert pipeline["OpenShellVerifyMainAfterDone"]["on_error"] == ["OpenShellAbort"]
    assert business_next(pipeline["OpenShellReturnFromCategory"]) == [
        "OpenShellVerifyMainAfterDone"
    ]

    from agent.runtime_state import daily_routine_state, green_wild_daily_state
    from agent.my_reco import CheckGreenWildDailyPendingReco
    from agent.my_action import InitGreenWildDailyAction

    buy_fish_reco = CheckGreenWildDailyPendingReco()

    # ---- Case 2：一次返回直达主鱼缸 ----
    setup_standalone_context()
    sim = OpenShellExitSimulator(pipeline, buy_fish_reco).run_exit_after_done(MAIN_TANK)
    assert sim.outcome == "standalone_complete", sim.visited
    assert sim.visited[0] == "OpenShellVerifyMainAfterDone"
    assert "OpenShellReturnFromCategory" not in sim.visited
    assert sim.clicks == [], "主鱼缸路径不得产生任何多余点击"
    assert "OpenShellAbort" not in sim.visited
    print("[PASS] Case 2 一次返回直达主鱼缸：VerifyMain 直接命中，无多余 Click")

    # ---- Case 1：真实两级返回（独立上下文） ----
    setup_standalone_context()
    sim = OpenShellExitSimulator(pipeline, buy_fish_reco).run_exit_after_done(CATEGORY_PAGE)
    assert sim.outcome == "standalone_complete", sim.visited
    assert "OpenShellAbort" not in sim.visited, sim.visited
    assert sim.missed[0] == "OpenShellVerifyMainAfterDone", "分类页上 VerifyMain 必须先未命中"
    assert "OpenShellReturnFromCategory" in sim.visited
    assert sim.clicks == ["OpenShellReturnFromCategory"], sim.clicks
    assert sim.visited.count("OpenShellVerifyMainAfterDone") == 1
    assert sim.page == MAIN_TANK
    print("[PASS] Case 1 两级返回：分类页 -> 第二次返回 -> VerifyMain 确认主鱼缸，未 Abort")

    # ---- Case 3：GreenWildDaily 上下文，两级返回后继续买鱼 ----
    setup_standalone_context()
    daily_routine_state["active"] = True
    daily_routine_state["step"] = "GREEN_WILD_DAILY"
    assert InitGreenWildDailyAction().run(MockContext(), MockArg()) is True
    assert green_wild_daily_state["pending_buy_fish"] is True
    reco = CheckGreenWildDailyPendingReco()
    assert reco.analyze(MockContext(), MockArg()) == (0, 0, 10, 10)

    sim = OpenShellExitSimulator(pipeline, buy_fish_reco).run_exit_after_done(CATEGORY_PAGE)
    assert sim.outcome == "green_wild_buy_fish", sim.visited
    assert "OpenShellStandaloneComplete" not in sim.visited, sim.visited
    assert "OpenShellAbort" not in sim.visited
    assert sim.clicks == ["OpenShellReturnFromCategory"]
    assert sim.visited.count("OpenShellVerifyMainAfterDone") == 1
    print("[PASS] Case 3 GreenWildDaily：两级返回后 VerifyMain -> GreenWildDailyBuyFishEntry，未误走 Standalone")

    # ---- Case 4：独立 OpenShellTask，残留 pending 标记不得劫持 ----
    setup_standalone_context()
    green_wild_daily_state["pending_buy_fish"] = True  # 模拟上一次日常中断的残留标记
    assert CheckGreenWildDailyPendingReco().analyze(MockContext(), MockArg()) is None

    sim = OpenShellExitSimulator(pipeline, buy_fish_reco).run_exit_after_done(CATEGORY_PAGE)
    assert sim.outcome == "standalone_complete", sim.visited
    assert "GreenWildDailyOpenShop" not in sim.visited
    assert "OpenShellAbort" not in sim.visited
    assert sim.clicks == ["OpenShellReturnFromCategory"]
    print("[PASS] Case 4 Standalone：日常收尾未激活时残留 pending 不劫持，正常 OpenShellStandaloneComplete")

    daily_routine_state["active"] = False
    daily_routine_state["step"] = ""
    green_wild_daily_state["pending_buy_fish"] = False
    print("[PASS] OpenShell 退出状态机 4 项语义场景全部通过")


class OpenShellEntrySimulator:
    """按 Maa next 列表语义驱动真实 open_shell.json 入口链。

    页面识别语义依据：
    - OpenShellEntry（开贝壳_入口.png）只在主鱼缸命中，每次评估返回当帧最新 bbox
      （模拟重新截图/重新识别，bbox 逐次漂移，禁止复用旧坐标）；
    - OpenShellCategoryPage（开贝壳_误触识别.png）只在贝壳分类页命中（实测 1.0000）；
    - OpenShellEntryRetryOnMainTank（主界面特征.png）只在主鱼缸命中（分类页实测 0.357 MISS）；
    - OpenShellEnter（OCR “进入”）只在分类页命中（原有兜底语义保持）；
    - OpenShellEntryRetryGate 委托真实 CheckOpenShellEntryRetryReco 计数判定。
    """

    def __init__(self, pipeline, gate_reco, after_click, task_id=990000001):
        # after_click(click_index) -> 点击第 N 次入口后的真实页面：
        #   MAIN_TANK=点击被游鱼挡住未生效；CATEGORY_PAGE=成功进入；其它字符串=未知页面
        self.pipeline = pipeline
        self.gate_reco = gate_reco
        self.after_click = after_click
        self.task_id = task_id
        self.page = None
        self.visited = []
        self.entry_recognitions = []   # 每次 OpenShellEntry 识别返回的 bbox（按序）
        self.entry_clicks = []         # (节点名, 本次点击实际使用的 bbox)
        self.pending_bbox = None
        self.outcome = None

    def _eval(self, name):
        """评估一个 next 候选是否识别命中；OpenShellEntry 命中时记录最新 bbox。"""
        if name == "OpenShellEntry":
            if self.page != MAIN_TANK:
                return False
            # 每次都重新截图识别：bbox 逐次漂移，模拟鱼游动导致的匹配位置变化
            bbox = [339 + 7 * len(self.entry_recognitions), 542, 68, 39]
            self.entry_recognitions.append(list(bbox))
            self.pending_bbox = bbox
            return True
        if name == "OpenShellCategoryPage":
            return self.page == CATEGORY_PAGE
        if name == "OpenShellEntryRetryOnMainTank":
            return self.page == MAIN_TANK
        if name == "OpenShellEnter":
            return self.page == CATEGORY_PAGE
        if name == "OpenShellEntryRetryGate":
            param = self.pipeline[name].get("custom_recognition_param") or {}
            return (
                self.gate_reco.analyze(MockContext(), MockArg(param, task_id=self.task_id))
                is not None
            )
        if name == "OpenShellAbort":
            return True  # DirectHit
        raise AssertionError(f"入口链意外到达节点: {name}")

    def _follow(self, name):
        self.visited.append(name)
        if name == "OpenShellEnter":
            # 入口阶段终点：已确认贝壳分类页，即将点击「进入」
            self.outcome = "entered_category"
            return
        node = self.pipeline[name]
        if node.get("action") == "StopTask":
            self.outcome = "abort_stop_task"
            return
        if node.get("action") == "Click":
            if name == "OpenShellEntry":
                click_index = len(self.entry_clicks) + 1
                self.entry_clicks.append((name, list(self.pending_bbox)))
                self.page = self.after_click(click_index)
        for cand in business_next(node):
            if self._eval(cand):
                self._follow(cand)
                return
        for cand in node.get("on_error", []):
            if self._eval(cand):
                self._follow(cand)
                return
        raise AssertionError(f"{name} 的 next 与 on_error 均未命中，入口链悬空")

    def run_from_main_tank(self):
        self.page = MAIN_TANK
        assert self._eval("OpenShellEntry"), "主鱼缸上入口模板必须可识别"
        self._follow("OpenShellEntry")
        return self


def run_entry_retry_tests():
    pipeline = json.loads(OPEN_SHELL_PATH.read_text(encoding="utf-8"))
    pipeline.update(json.loads(GREEN_WILD_PATH.read_text(encoding="utf-8")))

    # ---- 静态契约：入口节点参数保持不变，重试链使用独立门禁节点 ----
    entry = pipeline["OpenShellEntry"]
    assert entry["recognition"] == "TemplateMatch"
    assert entry["template"] == "开贝壳_入口.png"
    assert entry["threshold"] == 0.8
    assert entry["roi"] == [289, 492, 168, 139]
    assert entry["action"] == "Click"
    assert "target" not in entry
    assert business_next(entry) == [
        "OpenShellCategoryPage",
        "OpenShellEntryRetryOnMainTank",
        "OpenShellEnter",
    ]

    retry_node = pipeline["OpenShellEntryRetryOnMainTank"]
    assert retry_node["recognition"] == "TemplateMatch"
    assert retry_node["template"] == "主界面特征.png"
    assert retry_node["threshold"] == 0.7
    assert retry_node["roi"] == [0, 200, 150, 400]
    assert retry_node["action"] == "DoNothing", "重试门禁本身绝不下发点击"
    assert "target" not in retry_node
    assert 300 <= retry_node["post_delay"] <= 800, "重试等待必须在 300~800ms 区间"
    assert business_next(retry_node) == ["OpenShellEntryRetryGate"]
    assert retry_node.get("on_error") == ["OpenShellAbort"]

    gate = pipeline["OpenShellEntryRetryGate"]
    assert gate["recognition"] == "Custom"
    assert gate["custom_recognition"] == "CheckOpenShellEntryRetryReco"
    assert gate["action"] == "DoNothing"
    assert int(gate["custom_recognition_param"]["max_retries"]) >= 10, "上限必须宽松"
    assert business_next(gate) == ["OpenShellEntry"]
    assert gate.get("on_error") == ["OpenShellAbort"]

    # 独立任务与 GreenWildDaily 均收敛到统一启动 Router（入口重试语义两条路径一致）
    assert business_next(pipeline["OpenShellTask"]) == ["OpenShellStartRouter"]
    assert business_next(pipeline["GreenWildDailyTask"]) == ["OpenShellStartRouter"]
    start_router_next = business_next(pipeline["OpenShellStartRouter"])
    assert start_router_next == [
        "OpenShellStartPage",
        "OpenShellCategoryPage",
        "OpenShellEntry",
        "OpenShellRetryEntryFromMainTank",
        "OpenShellAbort",
    ]

    import agent.my_reco as my_reco_mod
    from agent.my_reco import CheckOpenShellEntryRetryReco

    gate_reco = CheckOpenShellEntryRetryReco()

    def fresh_sim(after_click, task_id=990000001):
        my_reco_mod.open_shell_entry_retry_state = {"task_id": None, "retries": 0}
        return OpenShellEntrySimulator(pipeline, gate_reco, after_click, task_id)

    # ---- E1：第一次点击即成功 ----
    sim = fresh_sim(lambda n: CATEGORY_PAGE).run_from_main_tank()
    assert sim.outcome == "entered_category", sim.visited
    assert len(sim.entry_clicks) == 1
    assert "OpenShellEntryRetryOnMainTank" not in sim.visited
    assert "OpenShellAbort" not in sim.visited
    print("[PASS] E1 第一次点击即成功：单次点击直达分类页，未进入重试")

    # ---- E2：第一次被鱼挡住，第二次成功；重试必须用重新识别的 bbox ----
    buf = StringIO()
    with redirect_stdout(buf):
        sim = fresh_sim(lambda n: CATEGORY_PAGE if n >= 2 else MAIN_TANK).run_from_main_tank()
    assert sim.outcome == "entered_category", sim.visited
    assert len(sim.entry_clicks) == 2, sim.entry_clicks
    assert sim.visited.count("OpenShellEntryRetryOnMainTank") == 1
    assert "OpenShellAbort" not in sim.visited
    for i, (_, bbox) in enumerate(sim.entry_clicks):
        assert bbox == sim.entry_recognitions[i], "每次点击必须使用当次重新识别的 bbox"
    assert sim.entry_clicks[0][1] != sim.entry_clicks[1][1], "禁止重复点击旧坐标"
    assert buf.getvalue().count("入口点击未生效") == 1
    print("[PASS] E2 被挡一次后重试成功：第二次点击使用重新识别的新 bbox，未 Abort")

    # ---- E3：连续 3 次被挡后成功，不得提前 Abort ----
    sim = fresh_sim(lambda n: CATEGORY_PAGE if n >= 4 else MAIN_TANK).run_from_main_tank()
    assert sim.outcome == "entered_category", sim.visited
    assert len(sim.entry_clicks) == 4
    assert sim.visited.count("OpenShellEntryRetryOnMainTank") == 3
    assert "OpenShellAbort" not in sim.visited
    print("[PASS] E3 连续 3 次被挡后成功：持续重试不提前 Abort")

    # ---- E4：永远被挡 -> 宽松上限后安全熔断 ----
    max_retries = int(pipeline["OpenShellEntryRetryGate"]["custom_recognition_param"]["max_retries"])
    buf = StringIO()
    with redirect_stdout(buf):
        sim = fresh_sim(lambda n: MAIN_TANK).run_from_main_tank()
    assert sim.outcome == "abort_stop_task", sim.visited
    assert len(sim.entry_clicks) == max_retries + 1, sim.entry_clicks
    assert sim.visited.count("OpenShellEntryRetryOnMainTank") == max_retries + 1
    assert f"入口重试已达上限 ({max_retries})" in buf.getvalue()
    print(f"[PASS] E4 永远被挡：重试 {max_retries} 次后安全熔断 Abort，不无限循环")

    # ---- E5：点击后落在未知页面 -> 不再盲点入口，保持安全失败 ----
    sim = fresh_sim(lambda n: "unknown").run_from_main_tank()
    assert sim.outcome == "abort_stop_task", sim.visited
    assert len(sim.entry_clicks) == 1, "未知页面上不得再次点击入口"
    assert len(sim.entry_recognitions) == 1, "未知页面上不得再次识别/点击入口"
    assert "OpenShellEntryRetryOnMainTank" not in sim.visited, "未知页面不得判为主鱼缸"
    print("[PASS] E5 未知页面：不重试不盲点，走原有 Abort 安全失败")

    # ---- E6：计数按 task_id 隔离，新任务运行自动归零 ----
    my_reco_mod.open_shell_entry_retry_state = {"task_id": None, "retries": 0}
    assert gate_reco.analyze(MockContext(), MockArg({"max_retries": 15}, task_id=111)) is not None
    assert gate_reco.analyze(MockContext(), MockArg({"max_retries": 15}, task_id=111)) is not None
    assert my_reco_mod.open_shell_entry_retry_state["retries"] == 2
    assert gate_reco.analyze(MockContext(), MockArg({"max_retries": 15}, task_id=222)) is not None
    assert my_reco_mod.open_shell_entry_retry_state == {"task_id": 222, "retries": 1}
    my_reco_mod.open_shell_entry_retry_state = {"task_id": None, "retries": 0}
    print("[PASS] E6 重试计数按 task_id 隔离，新任务自动归零")

    print("[PASS] OpenShell 入口重试状态机 6 项语义场景全部通过")




class OpenShellStartSimulator:
    """按 Maa next 列表语义驱动 OpenShellStartRouter 启动循环。

    每轮 Router 评估 = 一次新截图（frame_fn(round) 返回当帧状态）：
      page: MAIN / CATEGORY / OCTOPUS / UNKNOWN
      entry_visible: 主鱼缸上开贝壳_入口.png 是否命中（鱼遮挡模拟）
    """

    def __init__(self, pipeline, frame_fn, task_id=980000001):
        self.pipeline = pipeline
        self.frame_fn = frame_fn
        self.task_id = task_id
        self.page = None
        self.entry_visible = None
        self.rounds = 0            # Router 评估轮数（= 截图次数）
        self.retries = 0           # 主鱼缸重试命中次数
        self.visited = []
        self.entry_clicks = 0
        self.outcome = None

    def reco_hit(self, name):
        if name in ("OpenShellTask", "GreenWildDailyTask", "OpenShellStartRouter"):
            return True  # DirectHit
        if name == "OpenShellStartPage":
            return self.page == "octopus"
        if name == "OpenShellCategoryPage":
            return self.page == "category"
        if name == "OpenShellEntry":
            return self.page == "main" and self.entry_visible
        if name == "OpenShellRetryEntryFromMainTank":
            return self.page == "main"  # 主界面特征门禁
        if name == "OpenShellAbort":
            return True
        raise AssertionError(f"启动链意外到达节点: {name}")

    def _follow(self, name):
        self.visited.append(name)
        if name == "OpenShellStartRouter":
            # 每次进入 Router = 一次新截图（框架对 next 列表的重新评估）
            self.rounds += 1
            self.page, self.entry_visible = self.frame_fn(self.rounds)
        node = self.pipeline[name]
        if node.get("action") == "StopTask":
            self.outcome = "stop_task"
            return
        if node.get("action") == "Click" and name == "OpenShellEntry":
            self.entry_clicks += 1
            self.outcome = "entry_clicked"
            return
        if name == "OpenShellStartPage":
            self.outcome = "resume_octopus"
            return
        if name == "OpenShellCategoryPage":
            self.outcome = "resume_category"
            return
        if name == "OpenShellRetryEntryFromMainTank":
            self.retries += 1
        for cand in business_next(node):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        raise AssertionError(f"{name} 的 next 未命中，启动链悬空")

    def run(self, task_entry="OpenShellTask"):
        self._follow(task_entry)
        return self


def run_start_retry_tests():
    pipeline = json.loads(OPEN_SHELL_PATH.read_text(encoding="utf-8"))
    pipeline.update(json.loads(GREEN_WILD_PATH.read_text(encoding="utf-8")))

    def fresh(frames, task_entry="OpenShellTask"):
        it = {"n": 0}

        def frame_fn(round_no):
            it["n"] = round_no
            return frames[min(round_no - 1, len(frames) - 1)]

        sim = OpenShellStartSimulator(pipeline, frame_fn)
        sim._follow(task_entry)
        return sim

    # ---- Case 1：首帧入口被挡，第二帧出现 → Retry 后点击 ----
    sim = fresh([("main", False), ("main", True)])
    assert sim.outcome == "entry_clicked", sim.visited
    assert sim.retries == 1
    assert sim.rounds == 2, "第二帧必须重新截图评估"
    assert "OpenShellAbort" not in sim.visited
    print("[PASS] Start Case 1 入口首帧 miss：主鱼缸确认 → 等待 → 第二帧识别并点击")

    # ---- Case 2：连续 3 帧被挡，第 4 帧出现 ----
    sim = fresh([("main", False), ("main", False), ("main", False), ("main", True)])
    assert sim.outcome == "entry_clicked"
    assert sim.retries == 3
    assert sim.rounds == 4
    assert "OpenShellAbort" not in sim.visited
    print("[PASS] Start Case 2 连续 3 帧被挡：持续等待重试不提前 Abort，第 4 帧成功")

    # ---- Case 4：已在分类页 → 直接继续，不走主鱼缸重试 ----
    sim = fresh([("category", False)])
    assert sim.outcome == "resume_category"
    assert sim.retries == 0
    print("[PASS] Start Case 4 已在分类页：直接继续（CategoryPage 门禁优先）")

    # ---- Case 5：已在大章鱼页 → 直接继续 ----
    sim = fresh([("octopus", False)])
    assert sim.outcome == "resume_octopus"
    assert sim.retries == 0
    print("[PASS] Start Case 5 已在大章鱼页：直接继续（StartPage 门禁优先）")

    # ---- Case 6：未知页面 → 四候选全 miss 才 Abort ----
    sim = fresh([("unknown", False)])
    assert sim.outcome == "stop_task"
    assert sim.retries == 0
    print("[PASS] Start Case 6 未知页面：StartPage/CategoryPage/Entry/MainTank 全 miss → Abort")

    # ---- 两个启动入口语义一致：GreenWildDailyTask 走同一 Router 同样重试成功 ----
    sim = fresh([("main", False), ("main", False), ("main", True)], task_entry="GreenWildDailyTask")
    assert sim.outcome == "entry_clicked"
    assert sim.retries == 2
    assert "OpenShellAbort" not in sim.visited
    print("[PASS] Start 双入口：GreenWildDailyTask 收敛到同一 StartRouter，重试语义与独立任务一致")

    print("[PASS] OpenShell 启动遮挡重试 5 项语义场景全部通过")


if __name__ == "__main__":
    run_tests()
    run_entry_retry_tests()
    run_start_retry_tests()
