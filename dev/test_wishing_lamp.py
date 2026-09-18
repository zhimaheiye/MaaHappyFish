# -*- coding: utf-8 -*-
"""许愿神灯（WishingLampTask）专项测试。

业务契约：
- 三态步骤可恢复启动（神灯内部 > 选择主页 > 主鱼缸入口），Deepest-First；
- 选择主页 OCR「神灯」点击文字本身进入灯内，以许愿绸模板确认；
- 许愿绸点击 N 次（post_delay 5s），计数 Reco 严格 N 次（无 off-by-one）；
- 两种模式：连续许愿（默认，LoopRouter 不含 PauseCheck）/ 遇暂停条件即停止（StopTask）；
- 完成后两级退出：神灯内 X → 确认选择主页 → X → 确认主鱼缸；
- 用户模板与 ROI 不得被改动。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
LAMP_PATH = ROOT / "assets/resource/pipeline/features/wishing_lamp.json"
INTERFACE_PATH = ROOT / "assets/interface.json"

GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]

MAIN_TANK = "main"
SELECT_PAGE = "select"   # 神灯选择主页（图一）
LAMP_PAGE = "lamp"       # 某个神灯内部（图二）
PAUSED_PAGE = "paused"   # 神灯内部 + 暂停条件图标出现


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


class MockTaskDetail:
    def __init__(self, task_id):
        self.task_id = task_id


class MockArg:
    def __init__(self, param=None, task_id=880000001):
        self.custom_action_param = json.dumps(param or {})
        self.custom_recognition_param = self.custom_action_param
        self.task_detail = MockTaskDetail(task_id)


class MockContext:
    pass


class WishingLampSimulator:
    """按 Maa next 列表语义驱动真实 wishing_lamp.json。"""

    def __init__(self, pipeline, page, loop_next=None, task_id=880000001, pause_after=None,
                 lamp_visible=True, on_swipe=None):
        # loop_next：模拟 interface 模式 override 注入的 LoopRouter.next（None = 原始）
        # pause_after：第 N 次许愿绸点击后暂停条件图标出现（模拟暂停模式场景）
        # lamp_visible：指定神灯是否在当前屏（OCR expected 命中前提）
        # on_swipe：每次滑动列表后的回调 round -> None（模拟滑动后目标灯出现）
        self.pipeline = pipeline
        self.page = page
        self.loop_next = loop_next
        self.task_id = task_id
        self.pause_after = pause_after
        self.lamp_visible = lamp_visible
        self.on_swipe = on_swipe
        self.swipe_count = 0
        self.max_swipes = 12
        self.visited = []
        self.clicks = []
        self.outcome = None

    def reco_hit(self, name):
        if name in ("WishingLampTask", "WishingLampStartRouter", "WishingLampLoopRouter",
                    "WishingLampDone"):
            return True  # DirectHit
        if name in ("WishingLampInLampPage", "WishingLampVerifyInLamp", "WishingLampClickSilk"):
            return self.page == LAMP_PAGE or self.page == PAUSED_PAGE  # 许愿绸模板
        if name in ("WishingLampSelectPage", "WishingLampVerifySelectPage",
                    "WishingLampVerifySelectPageAfterExit"):
            return self.page == SELECT_PAGE  # 许愿神灯_识别
        if name == "WishingLampMainTankEntry":
            return self.page == MAIN_TANK  # 许愿神灯_入口
        if name == "WishingLampOpenLamp":
            # OCR 指定灯名：只有目标灯在当前屏时命中
            return self.page == SELECT_PAGE and self.lamp_visible
        if name == "WishingLampSwipeLampList":
            # 选择主页门禁 + max_hit 12（超限后识别失败，由自身 on_error 安全停止）
            return self.page == SELECT_PAGE and self.swipe_count < self.max_swipes
        if name == "WishingLampVerifyMainTank":
            return self.page == MAIN_TANK  # 主界面特征
        if name == "WishingLampExitInner":
            return self.page in (LAMP_PAGE, PAUSED_PAGE)  # 灯内右上角 X
        if name == "WishingLampExitSelect":
            return self.page == SELECT_PAGE  # 选择主页右上角 X（同款模板同位置）
        if name == "WishingLampPauseCheck":
            return self.page == PAUSED_PAGE  # 暂停条件模板
        if name == "WishingLampShouldContinue":
            import agent.my_reco as m
            from agent.my_reco import CheckWishingLampContinueReco
            param = self.pipeline["WishingLampShouldContinue"].get("custom_recognition_param") or {}
            return CheckWishingLampContinueReco().analyze(
                MockContext(), MockArg(param, task_id=self.task_id)) is not None
        if name == "WishingLampAbort":
            return True  # DirectHit
        raise AssertionError(f"意外到达节点: {name}")

    def _next_list(self, node_name):
        if node_name == "WishingLampLoopRouter" and self.loop_next is not None:
            return [n for n in self.loop_next if n not in GLOBAL_HANDLERS]
        return business_next(self.pipeline[node_name])

    def _follow(self, name):
        self.visited.append(name)
        node = self.pipeline[name]
        if node.get("action") == "StopTask":
            self.outcome = "stop_task"
            return
        if node.get("action") == "Click":
            self.clicks.append(name)
            if name == "WishingLampClickSilk":
                self.page = LAMP_PAGE  # 点击许愿绸后仍在神灯内
                if self.pause_after is not None and                         self.clicks.count("WishingLampClickSilk") >= self.pause_after:
                    self.page = PAUSED_PAGE  # 暂停条件图标出现
            elif name == "WishingLampMainTankEntry":
                self.page = SELECT_PAGE  # 入口点击后进入选择主页
            elif name == "WishingLampOpenLamp":
                self.page = LAMP_PAGE  # 点击灯名后进入神灯内部
            elif name == "WishingLampExitInner":
                self.page = SELECT_PAGE  # 灯内退出后回到选择主页
            elif name == "WishingLampExitSelect":
                self.page = MAIN_TANK  # 选择主页退出后回到主鱼缸
        if name == "WishingLampSwipeLampList":
            # action=Swipe（非 Click），滑动计数独立处理
            self.swipe_count += 1
            if self.on_swipe:
                self.on_swipe(self.swipe_count)
        for cand in self._next_list(name):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        if business_next(node) and node.get("on_error"):
            # active node 的 next 候选全 miss = 节点识别失败（如 SwipeLampList max_hit 耗尽）
            # → 触发自身 on_error
            for cand in node.get("on_error", []):
                if self.reco_hit(cand):
                    self._follow(cand)
                    return
        # 节点成功执行且 next 为空 = 任务正常收尾
        self.outcome = "chain_end"

    def run(self, page):
        self.page = page
        self._follow("WishingLampTask")
        return self


def run_tests():
    pipeline = json.loads(LAMP_PATH.read_text(encoding="utf-8"))
    interface = json.loads(INTERFACE_PATH.read_text(encoding="utf-8"))

    # ---- 模板与 ROI 契约（用户提供的值，不得改动）----
    tpl_specs = {
        "WishingLampMainTankEntry": ("许愿神灯_入口.png", [145, 171, 35, 22], "Click"),
        "WishingLampSelectPage": ("许愿神灯_识别.png", [0, 0, 201, 129], "DoNothing"),
        "WishingLampVerifySelectPage": ("许愿神灯_识别.png", [0, 0, 201, 129], "DoNothing"),
        "WishingLampVerifySelectPageAfterExit": ("许愿神灯_识别.png", [0, 0, 201, 129], "DoNothing"),
        "WishingLampInLampPage": ("许愿绸.png", [1022, 458, 68, 38], "DoNothing"),
        "WishingLampVerifyInLamp": ("许愿绸.png", [1022, 458, 68, 38], "DoNothing"),
        "WishingLampClickSilk": ("许愿绸.png", [1022, 458, 68, 38], "Click"),
        "WishingLampPauseCheck": ("许愿神灯_暂停条件.png", [583, 135, 130, 127], "StopTask"),
        "WishingLampExitInner": ("许愿神灯_退出.png", [1226, 22, 38, 37], "Click"),
        "WishingLampExitSelect": ("许愿神灯_退出.png", [1226, 22, 38, 37], "Click"),
    }
    for node_name, (tpl, roi, action) in tpl_specs.items():
        node = pipeline[node_name]
        assert node["recognition"] == "TemplateMatch"
        assert node["template"] == tpl, node_name
        assert node["roi"] == roi, node_name
        assert node["threshold"] == 0.8, node_name
        assert node["action"] == action, node_name
        if action == "Click" and node_name != "WishingLampOpenLamp":
            assert "target" not in node, f"{node_name} 必须点击识别位置"
    assert pipeline["WishingLampVerifyMainTank"]["template"] == "主界面特征.png"
    assert pipeline["WishingLampVerifyMainTank"]["roi"] == [0, 200, 150, 400]
    ocr = pipeline["WishingLampOpenLamp"]
    assert ocr["recognition"] == "OCR" and ocr["expected"] == "幸运神灯", "默认目标灯为幸运神灯（interface 可 override）"
    assert ocr["roi"] == [68, 459, 1213, 83]
    assert ocr["action"] == "Click" and "target" not in ocr, "灯名必须点击 OCR 文字本身"
    assert business_next(pipeline["WishingLampSelectPage"]) == [
        "WishingLampOpenLamp", "WishingLampSwipeLampList"]
    swipe = pipeline["WishingLampSwipeLampList"]
    assert swipe["recognition"] == "TemplateMatch"
    assert swipe["template"] == "许愿神灯_识别.png", "滑动前必须确认仍在选择主页"
    assert swipe["action"] == "Swipe"
    assert swipe["begin"] == [1000, 360] and swipe["end"] == [280, 360]
    assert swipe["max_hit"] == 12, "滑动上限必须宽松（12 次）"
    assert swipe["on_error"] == ["WishingLampAbort"]
    assert business_next(swipe) == ["WishingLampOpenLamp", "WishingLampSwipeLampList"]
    assert pipeline["WishingLampClickSilk"]["post_delay"] == 5000, "许愿绸点击后等待 5 秒"
    for name in ("许愿神灯_入口.png", "许愿神灯_识别.png", "许愿绸.png",
                 "许愿神灯_退出.png", "许愿神灯_暂停条件.png"):
        assert (ROOT / "assets/resource/image" / name).is_file()
    print("[PASS] 模板/ROI/OCR 契约：用户提供的坐标原样接入，灯名点击文字本身，5 秒等待")

    # ---- StartRouter 三态 deepest-first ----
    start_next = business_next(pipeline["WishingLampStartRouter"])
    assert start_next == ["WishingLampInLampPage", "WishingLampSelectPage", "WishingLampMainTankEntry", "WishingLampAbort"]
    print("[PASS] StartRouter 三态恢复：神灯内部 > 选择主页 > 主鱼缸入口")

    # ---- 退出两级门禁链 ----
    assert business_next(pipeline["WishingLampDone"]) == ["WishingLampExitInner"]
    assert business_next(pipeline["WishingLampExitInner"]) == ["WishingLampVerifySelectPageAfterExit"]
    assert business_next(pipeline["WishingLampVerifySelectPageAfterExit"]) == ["WishingLampExitSelect"]
    assert business_next(pipeline["WishingLampExitSelect"]) == ["WishingLampVerifyMainTank"]
    assert pipeline["WishingLampVerifyMainTank"].get("on_error") == ["WishingLampAbort"]
    print("[PASS] 退出链：灯内 X -> 确认选择主页 -> X -> 确认主鱼缸")

    # ---- 计数 Reco：严格 N 次，无 off-by-one ----
    import agent.runtime_state as rs
    from agent.my_reco import CheckWishingLampContinueReco
    reco = CheckWishingLampContinueReco()

    for target in (1, 10):
        rs.wishing_lamp_state = {"task_id": None, "completed": 0, "target": target}
        hits = 0
        for _ in range(target + 5):
            if reco.analyze(MockContext(), MockArg({"target_count": target}, task_id=100 + target)) is not None:
                hits += 1
            else:
                break
        assert hits == target, f"target={target} 但命中 {hits} 次"
        # 再评估一次仍为 None（稳定流向 Done）
        assert reco.analyze(MockContext(), MockArg({"target_count": target}, task_id=100 + target)) is None
    import agent.my_reco as my_reco_mod
    my_reco_mod.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    # task_id 隔离：新任务计数归零（reco 的 global 绑定在 my_reco 模块命名空间）
    reco.analyze(MockContext(), MockArg({"target_count": 10}, task_id=2))
    reco.analyze(MockContext(), MockArg({"target_count": 10}, task_id=2))
    reco.analyze(MockContext(), MockArg({"target_count": 10}, task_id=3))
    assert my_reco_mod.wishing_lamp_state == {"task_id": 3, "completed": 1, "target": 10}
    my_reco_mod.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    print("[PASS] 计数 Reco：target=N 恰好命中 N 次（1 与 10 均验证），task_id 隔离")

    # ---- 语义场景 1：从主鱼缸启动，连续许愿 10 次，两级退出 ----
    sim = WishingLampSimulator(pipeline, MAIN_TANK).run(MAIN_TANK)
    assert sim.outcome == "chain_end"  # VerifyMainTank 无 next，正常收尾
    silk_clicks = sim.clicks.count("WishingLampClickSilk")
    assert silk_clicks == 10, silk_clicks
    assert "WishingLampOpenLamp" in sim.visited  # 主鱼缸 → 入口 → 选择页 → 点灯名
    assert "WishingLampExitInner" in sim.visited and "WishingLampExitSelect" in sim.visited
    assert sim.visited[-1] == "WishingLampVerifyMainTank"
    assert "WishingLampAbort" not in sim.visited
    print("[PASS] 场景 1：主鱼缸启动 → 点灯名 → 许愿 10 次 → 两级退出确认主鱼缸")

    # ---- 语义场景 2：已在选择主页启动 ----
    import agent.my_reco as m
    m.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    sim = WishingLampSimulator(pipeline, SELECT_PAGE).run(SELECT_PAGE)
    assert sim.clicks.count("WishingLampClickSilk") == 10
    assert "WishingLampMainTankEntry" not in sim.visited
    assert sim.visited[-1] == "WishingLampVerifyMainTank"
    print("[PASS] 场景 2：选择主页启动（无需点入口），许愿后正常退出")

    # ---- 语义场景 3：已在神灯内部启动（最深恢复）----
    m.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    sim = WishingLampSimulator(pipeline, LAMP_PAGE).run(LAMP_PAGE)
    assert "WishingLampOpenLamp" not in sim.visited and "WishingLampMainTankEntry" not in sim.visited
    assert sim.clicks.count("WishingLampClickSilk") == 10
    assert sim.visited[-1] == "WishingLampVerifyMainTank"
    print("[PASS] 场景 3：神灯内部启动（最深优先），直接许愿后退出")

    # ---- 语义场景 4：暂停模式命中 → StopTask ----
    my_reco_mod.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    pause_next = GLOBAL_HANDLERS + ["WishingLampPauseCheck", "WishingLampShouldContinue", "WishingLampDone"]
    sim = WishingLampSimulator(pipeline, LAMP_PAGE, loop_next=pause_next, pause_after=3)
    sim.run(LAMP_PAGE)
    assert sim.outcome == "stop_task", sim.visited
    assert sim.clicks.count("WishingLampClickSilk") == 3  # 暂停前点了 3 次
    assert "WishingLampPauseCheck" in sim.visited
    assert "WishingLampExitInner" not in sim.visited  # 不再退出，等待用户处理
    print("[PASS] 场景 4：暂停模式下识别到暂停条件 → StopTask 等待用户处理，不再退出")

    # ---- 语义场景 5：连续模式（默认 case 的 override 生效）暂停条件不可达 ----
    m.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 5}
    my_reco_mod.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    cont_next = GLOBAL_HANDLERS + ["WishingLampShouldContinue", "WishingLampDone"]
    sim = WishingLampSimulator(pipeline, PAUSED_PAGE, loop_next=cont_next)  # 页面有暂停图标也不检查
    sim.run(PAUSED_PAGE)
    assert "WishingLampPauseCheck" not in sim.visited, "连续模式不得检查暂停条件"
    assert sim.clicks.count("WishingLampClickSilk") == 10  # 节点默认参数 10 次
    assert sim.visited[-1] == "WishingLampVerifyMainTank"
    print("[PASS] 场景 5：连续模式（默认）不识别暂停条件，即使图标在页面也不受影响")

    # ---- 场景 6：指定灯不在当前屏 → 滑动 2 次后找到 ----
    my_reco_mod.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    sim = WishingLampSimulator(
        pipeline, SELECT_PAGE, lamp_visible=False,
        on_swipe=lambda rnd: setattr(sim, "lamp_visible", rnd >= 2),
    )
    sim.run(SELECT_PAGE)
    assert sim.swipe_count == 2, sim.swipe_count
    assert sim.clicks.count("WishingLampOpenLamp") == 1
    assert sim.outcome == "chain_end" and sim.visited[-1] == "WishingLampVerifyMainTank"
    assert "WishingLampAbort" not in sim.visited
    print("[PASS] 场景 6 目标灯不在当前屏：向左滑动 2 次后 OCR 命中并进入，正常许愿退出")

    # ---- 场景 7：滑动 12 次仍找不到 → max_hit 耗尽 → 安全停止 ----
    my_reco_mod.wishing_lamp_state = {"task_id": None, "completed": 0, "target": 10}
    sim = WishingLampSimulator(pipeline, SELECT_PAGE, lamp_visible=False)
    sim.run(SELECT_PAGE)
    assert sim.swipe_count == 12
    assert sim.outcome == "stop_task"  # SwipeLampList 自身 on_error → Abort
    assert sim.clicks.count("WishingLampOpenLamp") == 0
    print("[PASS] 场景 7 滑动 12 次仍未找到指定灯：max_hit 耗尽 → 安全停止，不无限循环")

    # ---- interface 契约 ----
    task = next(t for t in interface["task"] if t["entry"] == "WishingLampTask")
    assert task["name"] == "许愿神灯"
    assert task["default_check"] is False
    assert task["option"] == ["许愿神灯选择", "许愿神灯许愿次数", "许愿神灯模式"]
    lamp_opt = interface["option"]["许愿神灯选择"]
    lamp_names = [c["name"] for c in lamp_opt["cases"]]
    assert lamp_names == ["幸运神灯", "开心神灯", "欢乐神灯", "魔法神灯", "青春神灯", "奇迹神灯",
                          "活力神灯", "欢欣神灯", "玲珑神灯", "元气神灯", "童趣神灯"]
    assert lamp_opt["default_case"] == "幸运神灯"
    for case in lamp_opt["cases"]:
        assert case["pipeline_override"]["WishingLampOpenLamp"]["expected"] == case["name"]
    count_opt = interface["option"]["许愿神灯许愿次数"]
    counts = {}
    for case in count_opt["cases"]:
        counts[case["name"]] = case["pipeline_override"]["WishingLampShouldContinue"]["custom_recognition_param"]["target_count"]
    assert counts == {"5 次": 5, "10 次（默认）": 10, "20 次": 20, "50 次": 50}
    assert count_opt["default_case"] == "10 次（默认）"
    mode_opt = interface["option"]["许愿神灯模式"]
    mode_nexts = {c["name"]: c["pipeline_override"]["WishingLampLoopRouter"]["next"] for c in mode_opt["cases"]}
    cont = [n for n in mode_nexts["连续许愿（默认）"] if n not in GLOBAL_HANDLERS]
    pause = [n for n in mode_nexts["遇暂停条件即停止"] if n not in GLOBAL_HANDLERS]
    assert cont == ["WishingLampShouldContinue", "WishingLampDone"]
    assert pause == ["WishingLampPauseCheck", "WishingLampShouldContinue", "WishingLampDone"]
    assert mode_opt["default_case"] == "连续许愿（默认）"
    # 原始 Pipeline（未 override）的 LoopRouter 与暂停模式一致：模板默认接入但连续模式经 override 摘除
    orig_loop = business_next(pipeline["WishingLampLoopRouter"])
    assert orig_loop == ["WishingLampPauseCheck", "WishingLampShouldContinue", "WishingLampDone"]
    print("[PASS] interface 契约：任务条目、次数 4 档、模式双选 override 正确")

    print("[PASS] 许愿神灯专项测试全部通过")


if __name__ == "__main__":
    run_tests()
