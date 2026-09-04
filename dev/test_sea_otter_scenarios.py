#!/usr/bin/env python3
"""
验证 SeaOtterGemTask 核心状态机 4 大业务场景 (Mock/Replay)
"""
import sys
sys.path.insert(0, '.')

from agent.runtime_state import sea_otter_gem_state

class MockController:
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
        self.tasker = Tasker(ctrl)

# Import real actions
from agent.my_action import InitSeaOtterStateAction, SeaOtterHarvestAction, SeaOtterAdvancePairAction
from agent.my_reco import CheckSeaOtterLimitReco

init_act = InitSeaOtterStateAction()
harvest_act = SeaOtterHarvestAction()
advance_act = SeaOtterAdvancePairAction()
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


if __name__ == "__main__":
    test_scenario_a()
    test_scenario_b()
    test_scenario_c()
    test_scenario_d()
    print("\n>>> ALL 4 SCENARIOS 100% PASSED! <<<")
