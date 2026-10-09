#!/usr/bin/env python3
"""
验证 SeaOtterGemTask 核心状态机 4 大业务场景 (Mock/Replay)
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, '.')

from agent.runtime_state import sea_otter_gem_state

class MockController:
    succeeded = True
    def __init__(self):
        self.actions = []

    def post_touch_down(self, x, y):
        self.actions.append(f"TOUCH_DOWN({x}, {y})")
        return self
    def post_touch_up(self, contact):
        self.actions.append(f"TOUCH_UP({contact})")
        return self
    def post_click(self, x, y):
        if x == 1205:
            self.actions.append("CLICK_NEXT")
        elif x == 1085:
            self.actions.append("CLICK_PREV")
        else:
            self.actions.append(f"CLICK({x}, {y})")
        return self
    def wait(self):
        return self

class MockContext:
    def __init__(self, ctrl):
        class Tasker:
            def __init__(self, c):
                self.controller = c
                self.running = True
                self.stopping = False
        self.tasker = Tasker(ctrl)


class MockArg:
    def __init__(self, custom_action_param=None):
        self.custom_action_param = custom_action_param
        self.task_detail = None

# Import real actions
from agent.my_action import (
    InitSeaOtterStateAction,
    SeaOtterHarvestAction,
    SeaOtterAdvancePairAction,
    SeaOtterReturnFromRecommendedAction,
    SeaOtterBoundaryIncompleteAction,
    SeaOtterHomeReturnClickAction,
)
from agent.my_reco import CheckSeaOtterLimitReco

init_act = InitSeaOtterStateAction()
harvest_act = SeaOtterHarvestAction()
advance_act = SeaOtterAdvancePairAction()
recommended_bridge_act = SeaOtterReturnFromRecommendedAction()
limit_reco = CheckSeaOtterLimitReco()

def step(ctrl, ctx, ui_state):
    """
    Simulates one entry to SeaOtterFriendRouter.
    ui_state: 'HARVESTABLE' or 'EXHAUSTED' or 'ADD_FRIEND'
    Returns: 'DONE' or 'CONTINUE'
    """
    if limit_reco.analyze(ctx, None) is not None:
        return 'LIMIT_DONE'

    if ui_state == 'ADD_FRIEND':
        return 'DONE'
    elif ui_state == 'EXHAUSTED':
        advance_act.run(ctx, None)
        return 'CONTINUE'
    elif ui_state == 'HARVESTABLE':
        harvest_act.run(ctx, None)
        return 'CONTINUE'
    elif ui_state == 'RECOMMENDED':
        return 'CONTINUE' if recommended_bridge_act.run(ctx, None) else 'DONE'
    else:
        raise ValueError(f"Unknown ui_state {ui_state}")


def test_scenario_a():
    """
    场景 A：
    LEFT harvestable, RIGHT harvestable
    要求：L摸 -> R摸 -> L摸 -> R摸
    """
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    # 4 轮交互
    expected_flow = [
        ('HARVESTABLE', 'left'),
        ('HARVESTABLE', 'right'),
        ('HARVESTABLE', 'left'),
        ('HARVESTABLE', 'right')
    ]

    for i, (ui, expected_side) in enumerate(expected_flow):
        assert sea_otter_gem_state["current_side"] == expected_side, f"Step {i}: expected side {expected_side}, got {sea_otter_gem_state['current_side']}"
        res = step(ctrl, ctx, ui)
        assert res == 'CONTINUE'

    # Check controller actions
    # L: TOUCH -> NEXT
    # R: TOUCH -> PREV
    # L: TOUCH -> NEXT
    # R: TOUCH -> PREV
    clicks = [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')]
    assert clicks == ['CLICK_NEXT', 'CLICK_PREV', 'CLICK_NEXT', 'CLICK_PREV'], f"Clicks: {clicks}"
    assert sea_otter_gem_state["total_harvests"] == 4
    print("[PASS] Scenario A: L摸 -> R摸 -> L摸 -> R摸 验证通过！")


def test_scenario_b():
    """
    场景 B：
    LEFT harvestable, RIGHT exhausted
    要求：L摸 -> R不摸 -> L摸 -> R不摸，绝不 advance，绝不 Done
    """
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    # 4 轮交互
    # L(H) -> R(E) -> L(H) -> R(E)
    expected_flow = [
        ('HARVESTABLE', 'left'),
        ('EXHAUSTED', 'right'),
        ('HARVESTABLE', 'left'),
        ('EXHAUSTED', 'right')
    ]

    for i, (ui, expected_side) in enumerate(expected_flow):
        assert sea_otter_gem_state["current_side"] == expected_side, f"Step {i}: expected side {expected_side}, got {sea_otter_gem_state['current_side']}"
        res = step(ctrl, ctx, ui)
        assert res == 'CONTINUE', f"Step {i} resulted in premature {res}"

    # Clicks should be: NEXT (from L harvest), PREV (from R exhausted bridge), NEXT (from L harvest), PREV (from R exhausted bridge)
    clicks = [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')]
    assert clicks == ['CLICK_NEXT', 'CLICK_PREV', 'CLICK_NEXT', 'CLICK_PREV'], f"Clicks: {clicks}"
    # Harvest count should be 2 (only L harvested)
    assert sea_otter_gem_state["total_harvests"] == 2
    # Current side should be left
    assert sea_otter_gem_state["current_side"] == "left"
    print("[PASS] Scenario B: L摸 -> R不摸 -> L摸 -> R不摸 验证通过！")


def test_scenario_c():
    """
    场景 C：
    LEFT exhausted, RIGHT exhausted, NEXT FRIEND harvestable
    要求：
    L1 exhausted -> Next -> L2(old R, new LEFT,仍 exhausted) -> Next -> L3(new friend, harvestable) -> harvest
    绝不在旧 pair 循环
    """
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    # 1. L1 exhausted
    assert sea_otter_gem_state["current_side"] == "left"
    res1 = step(ctrl, ctx, 'EXHAUSTED')
    assert res1 == 'CONTINUE'
    # side stays left (target is now friend 2, treated as new LEFT)
    assert sea_otter_gem_state["current_side"] == "left"

    # 2. L2 (old R) is also exhausted
    res2 = step(ctrl, ctx, 'EXHAUSTED')
    assert res2 == 'CONTINUE'
    # side stays left (target is now friend 3, treated as new LEFT)
    assert sea_otter_gem_state["current_side"] == "left"

    # 3. L3 is harvestable
    res3 = step(ctrl, ctx, 'HARVESTABLE')
    assert res3 == 'CONTINUE'
    # L3 was harvested, side now transitions to right (friend 4)!
    assert sea_otter_gem_state["current_side"] == "right"

    clicks = [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')]
    # L1 exhausted -> CLICK_NEXT
    # L2 exhausted -> CLICK_NEXT
    # L3 harvest -> CLICK_NEXT
    assert clicks == ['CLICK_NEXT', 'CLICK_NEXT', 'CLICK_NEXT'], f"Clicks: {clicks}"
    assert sea_otter_gem_state["total_harvests"] == 1
    print("[PASS] Scenario C: L1(E)->L2(E)->L3(H) 自动推进验证通过！")


def test_scenario_d():
    """
    场景 D：
    新好友 harvestable，后来经过旧 exhausted 好友
    要求：
    旧 exhausted 只能作为当前控制逻辑中的桥/前移节点，绝不能触发全局 Done。
    """
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    # 模拟在多次滑动后，经过若干 exhausted 好友
    for _ in range(5):
        assert sea_otter_gem_state["current_side"] == "left"
        res = step(ctrl, ctx, 'EXHAUSTED')
        assert res == 'CONTINUE', "Exhausted node should NEVER cause Done!"

    # 遇到 harvestable 好友
    res = step(ctrl, ctx, 'HARVESTABLE')
    assert res == 'CONTINUE'
    assert sea_otter_gem_state["current_side"] == "right"

    # 遇右侧已耗尽好友，跳板回退
    res = step(ctrl, ctx, 'EXHAUSTED')
    assert res == 'CONTINUE'
    assert sea_otter_gem_state["current_side"] == "left"

    # 最终只有在真正看到 ADD_FRIEND 页面时才触发全局 Done
    res_done = step(ctrl, ctx, 'ADD_FRIEND')
    assert res_done == 'DONE', "ADD_FRIEND must trigger Done!"

    print("[PASS] Scenario D: 遇旧 exhausted 绝不误触 Done 验证通过！")


def test_scenario_e():
    """最后好友为 LEFT、推荐玩家为 RIGHT 时，推荐玩家只作为返回跳板。"""
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    expected_flow = [
        ('HARVESTABLE', 'left'),
        ('RECOMMENDED', 'right'),
        ('HARVESTABLE', 'left'),
        ('RECOMMENDED', 'right'),
    ]
    for ui, expected_side in expected_flow:
        assert sea_otter_gem_state["current_side"] == expected_side
        assert step(ctrl, ctx, ui) == 'CONTINUE'

    clicks = [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')]
    assert clicks == ['CLICK_NEXT', 'CLICK_PREV', 'CLICK_NEXT', 'CLICK_PREV']
    assert sea_otter_gem_state["total_harvests"] == 2
    assert sea_otter_gem_state["current_side"] == "left"
    print("[PASS] Scenario E: 最后好友与推荐玩家 LEFT/RIGHT 往返桥接验证通过！")


def test_scenario_f():
    """末位好友耗尽后进入推荐玩家页，不能当作寻宝体力全部耗尽。"""
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    assert step(ctrl, ctx, 'EXHAUSTED') == 'CONTINUE'
    assert sea_otter_gem_state["current_side"] == "left"
    assert step(ctrl, ctx, 'RECOMMENDED') == 'DONE'
    assert sea_otter_gem_state["completion_reason"] == "BOUNDARY_STAMINA_UNVERIFIED"
    assert not sea_otter_gem_state["normal_completion"]

    clicks = [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')]
    assert clicks == ['CLICK_NEXT'], "进入推荐玩家后不应再执行 Prev 或其他点击"
    print("[PASS] Scenario F: 推荐玩家边界报告未完成，零额外点击！")


def test_last_friend_gray_arrow_harvest():
    """灰色右键下摸宝后通过上一位刷新，再确认回到末位，不能原地空转。"""
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)

    ctx.run_recognition = lambda name, frame: SimpleNamespace(
        hit=(frame != 1 if name == "SeaOtterGrayRightArrow" else True),
        box=(45, 530, 80, 80),
    )
    with patch("agent.my_action._capture_720p", side_effect=[0, 1, 2]):
        assert harvest_act.run(ctx, MockArg({"refresh_last_friend": True}))
    assert sea_otter_gem_state["current_side"] == "left"
    assert sea_otter_gem_state["total_harvests"] == 1
    assert [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')] == [
        'CLICK_PREV', 'CLICK_NEXT'
    ]
    print("[PASS] 灰色右键末位好友经上一位刷新后返回！")


def test_last_friend_refresh_failure():
    """Prev 未生效时不穿透点 Next，也不累计摸宝或标记完整运行。"""
    ctrl = MockController()
    ctx = MockContext(ctrl)
    init_act.run(ctx, None)
    ctx.run_recognition = lambda name, frame: SimpleNamespace(hit=True, box=(45, 530, 80, 80))
    with patch("agent.my_action._capture_720p", return_value=0):
        assert not harvest_act.run(ctx, MockArg({"refresh_last_friend": True}))
    assert [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')] == ['CLICK_PREV']
    assert sea_otter_gem_state['total_harvests'] == 0
    assert not sea_otter_gem_state['normal_completion']
    assert sea_otter_gem_state['completion_reason'] == 'LAST_FRIEND_REFRESH_FAILED'


def test_last_friend_right_returns_to_original_left():
    """现场第105次 LEFT 摸取后的末位仍是 RIGHT，不能吃掉原 LEFT 的后续摸取。"""
    for exhausted in (False, True):
        ctrl = MockController()
        ctx = MockContext(ctrl)
        init_act.run(ctx, None)
        sea_otter_gem_state["current_side"] = "right"
        ctx.run_recognition = lambda name, frame: SimpleNamespace(
            hit=(frame == 0 if name == "SeaOtterGrayRightArrow" else True),
            box=(45, 530, 80, 80),
        )
        with patch("agent.my_action._capture_720p", side_effect=[0, 1]):
            if exhausted:
                assert SeaOtterBoundaryIncompleteAction().run(
                    ctx, MockArg({"reason": "LAST_FRIEND_STAMINA_UNVERIFIED"}))
            else:
                assert harvest_act.run(ctx, MockArg({"refresh_last_friend": True}))
        assert [a for a in ctrl.actions if a in ('CLICK_NEXT', 'CLICK_PREV')] == ['CLICK_PREV']
        assert sea_otter_gem_state["current_side"] == "left"
        assert sea_otter_gem_state["total_harvests"] == (0 if exhausted else 1)
        assert not sea_otter_gem_state["normal_completion"]
        # 原 LEFT 可以继续按普通往返摸取，不会提前停止。
        assert step(ctrl, ctx, 'HARVESTABLE') == 'CONTINUE'
        assert sea_otter_gem_state["total_harvests"] == (1 if exhausted else 2)


def test_last_friend_refresh_stop_and_empty_frame():
    """空帧零点击；点 Prev 后用户停止时不得补点 Next 或累计完整次数。"""
    for stop_after_prev in (False, True):
        ctrl = MockController()
        ctx = MockContext(ctrl)
        init_act.run(ctx, None)
        ctx.run_recognition = lambda name, frame: SimpleNamespace(hit=True, box=(45, 530, 80, 80))
        original_click = ctrl.post_click
        def click(x, y):
            result = original_click(x, y)
            ctx.tasker.stopping = True
            return result
        ctrl.post_click = click
        with patch('agent.my_action._capture_720p', return_value=(0 if stop_after_prev else None)):
            assert not harvest_act.run(ctx, MockArg({'refresh_last_friend': True}))
        assert sea_otter_gem_state['total_harvests'] == 0
        assert not sea_otter_gem_state['normal_completion']
        assert ('CLICK_NEXT' not in ctrl.actions)
        if not stop_after_prev:
            assert not ctrl.actions


def test_friend_gate_pipeline():
    pipeline_path = Path("assets/resource/pipeline/features/sea_otter_gem.json")
    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))

    def business_next(node_name):
        return [
            item for item in pipeline[node_name].get("next", [])
            if not item.startswith("[JumpBack]")
        ]

    first_friend = pipeline["SeaOtterStartFromFriendList"]
    assert first_friend["expected"] == "星级好友"
    assert first_friend["roi"] == [100, 90, 200, 60]
    assert first_friend["action"] == "Click"
    assert first_friend["target"] == [194, 262, 40, 40]
    assert "target" not in pipeline["SeaOtterStartAtFriendTank"]
    assert business_next("SeaOtterFriendRouter") == [
        "SeaOtterLimitReached",
        "SeaOtterHasStaminaPanel",
        "SeaOtterFriendLiked",
        "SeaOtterFriendUnliked",
        "SeaOtterAddFriendPage",
        "SeaOtterRecommendedBridge",
        "SeaOtterWaitScreen",
    ]
    add_friend = pipeline["SeaOtterAddFriendPage"]
    assert "不是你的好友" in add_friend["expected"]
    assert "加他为好友" in add_friend["expected"]
    assert "加好友邀请已经发出" in add_friend["expected"]
    assert add_friend["custom_action"] == "SeaOtterMarkNormalCompletionAction"
    assert business_next("SeaOtterAddFriendPage") == ["SeaOtterNonFriendBack"]
    assert pipeline["SeaOtterNonFriendBack"]["expected"] == "^返回$"
    assert pipeline["SeaOtterNonFriendBack"]["action"] == "Click"
    stamina_panel = pipeline["SeaOtterHasStaminaPanel"]
    assert stamina_panel["expected"] == ["剩余", "刷新体力"]
    assert stamina_panel["roi"] == [60, 210, 350, 170]
    assert business_next("SeaOtterHasStaminaPanel") == ["SeaOtterKnownFriendRouter"]
    harvest = pipeline["SeaOtterHarvestable"]
    assert harvest["roi"] == [0, 400, 560, 300]
    assert harvest["threshold"] == 0.65
    assert pipeline["SeaOtterFriendLiked"]["template"] == "好友判断_已点赞.png"
    assert pipeline["SeaOtterFriendUnliked"]["template"] == "好友判断_未点赞.png"
    assert business_next("SeaOtterFriendLiked") == ["SeaOtterKnownFriendRouter"]
    assert business_next("SeaOtterFriendUnliked") == ["SeaOtterKnownFriendRouter"]
    assert business_next("SeaOtterKnownFriendRouter") == [
        "SeaOtterGrayRightArrow",
        "SeaOtterExhausted",
        "SeaOtterHarvestable",
        "SeaOtterWaitScreen",
    ]
    gray_arrow = pipeline["SeaOtterGrayRightArrow"]
    assert gray_arrow["template"] == "好友切换_灰色右键.png"
    assert gray_arrow["roi"] == [1124, 0, 156, 134]
    assert Path("assets/resource/image/好友切换_灰色右键.png").is_file()
    assert business_next("SeaOtterGrayRightArrow") == [
        "SeaOtterLastFriendExhausted",
        "SeaOtterLastFriendHarvestable",
        "SeaOtterWaitScreen",
    ]
    assert business_next("SeaOtterLastFriendExhausted") == ["SeaOtterFriendRouter"]
    assert pipeline["SeaOtterLastFriendExhausted"]["on_error"] == ["SeaOtterHomeReturnRouter"]
    home = pipeline["SeaOtterHomeReturnRouter"]
    assert home["next"] == [
        "SeaOtterUnusedStaminaDialog",
        "SeaOtterHomeAtTank",
        "SeaOtterHomeAtPet",
        "SeaOtterHomeAtFriendList",
        "SeaOtterHomeAtFriendTank",
        "SeaOtterHomeAtGemExchange",
        "SeaOtterHomeReturnWait",
    ]
    dialog = pipeline["SeaOtterUnusedStaminaDialog"]
    assert dialog["action"] == "DoNothing"
    assert dialog["next"] == ["SeaOtterNavigationFailed"]
    assert "未使用的体力" in dialog["expected"]
    assert pipeline["SeaOtterHomeClickBack"]["custom_action"] == "SeaOtterHomeReturnClickAction"
    assert pipeline["SeaOtterHomeClickBack"]["expected"] == "^返回$"
    assert pipeline["SeaOtterHomeClickBack"]["roi"] == [0, 0, 189, 146]
    assert "target" not in pipeline["SeaOtterHomeClickBack"]
    assert pipeline["SeaOtterHomeAtTank"]["template"] == "主界面特征.png"
    assert pipeline["SeaOtterReturnedHome"]["action"] == "DoNothing"
    assert "SeaOtterDone" not in home["next"]
    assert "绿色勾选按钮.png" not in json.dumps(
        {name: pipeline[name] for name in home["next"]},
        ensure_ascii=False,
    )
    last_harvest = pipeline["SeaOtterLastFriendHarvestable"]
    assert last_harvest["roi"] == [0, 400, 560, 300]
    assert last_harvest["custom_action"] == "SeaOtterHarvestAction"
    assert last_harvest["custom_action_param"] == {"refresh_last_friend": True}
    assert last_harvest["on_error"] == ["SeaOtterNavigationFailed"]
    failure = pipeline["SeaOtterNavigationFailed"]
    assert failure["custom_action"] == "FailTaskAction"
    assert not failure.get("next") and not failure.get("on_error")
    assert business_next("SeaOtterLastFriendHarvestable") == ["SeaOtterFriendRouter"]
    bridge = pipeline["SeaOtterRecommendedBridge"]
    assert bridge["template"] == "好友_下一位.png"
    assert bridge["custom_action"] == "SeaOtterReturnFromRecommendedAction"
    assert bridge["on_error"] == ["SeaOtterNavigationFailed"]
    print("[PASS] 好友点赞双模板门禁与推荐玩家桥接 Pipeline 验证通过！")


def test_home_return_click_stays_in_corner():
    sea_otter_gem_state["home_return_ticks"] = 0
    ctrl = MockController()
    ctx = MockContext(ctrl)
    action = SeaOtterHomeReturnClickAction()

    def run_box(box):
        argv = MockArg()
        argv.box = box
        return action.run(ctx, argv)

    assert run_box((30, 23, 120, 53)) is True
    assert ctrl.actions == ["CLICK(90, 49)"]
    assert run_box((400, 300, 40, 40)) is False
    assert ctrl.actions == ["CLICK(90, 49)"]
    sea_otter_gem_state["home_return_ticks"] = 6
    assert run_box((30, 23, 120, 53)) is False
    assert ctrl.actions == ["CLICK(90, 49)"]
    sea_otter_gem_state["home_return_ticks"] = 0
    print("[PASS] 返回主鱼缸只点左上角返回，超次和偏点都停止")


if __name__ == "__main__":
    with patch("agent.my_action.time.sleep"):
        for name, test in sorted(list(globals().items())):
            if name.startswith("test_"):
                test()
                print(f"[PASS] {name}")
