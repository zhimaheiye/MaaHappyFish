# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import my_action


PIPELINE_PATH = ROOT / "assets/resource/pipeline/features/gem_gift_box.json"
GLOBAL_HANDLERS = {
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


def test_pipeline_contract():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert business_next(pipeline["GemGiftBoxTask"]) == [
        "GemGiftBoxUnexpectedDialog",
        "GemGiftBoxRun",
        "GemGiftBoxOpenEntry",
        "GemGiftBoxOpenTreasure",
    ]
    expected_templates = {
        "GemGiftBoxOpenTreasure": ("右下角_宝箱.png", [1120, 562, 141, 141]),
        "GemGiftBoxOpenEntry": ("宝石礼盒兑换入口.png", [828, 575, 132, 121]),
        "GemGiftBoxExchangeableMarker": ("宝石礼盒_可兑换.png", [587, 195, 47, 35]),
        "GemGiftBoxExchangeDialog": ("宝石礼盒_兑换识别.png", [771, 229, 200, 180]),
        "GemGiftBoxPlusButton": ("宝石礼盒兑换_点击.png", [878, 336, 134, 132]),
    }
    for node_name, (template, roi) in expected_templates.items():
        node = pipeline[node_name]
        assert node["template"] == template
        assert node["roi"] == roi
        assert (ROOT / "assets/resource/image" / template).is_file()

    assert pipeline["GemGiftBoxTopRecipe"]["expected"] == "16级配方"
    assert pipeline["GemGiftBoxTopRecipe"]["roi"] == [55, 196, 108, 41]
    assert pipeline["GemGiftBoxRun"]["expected"] == "兑换鱼配方数"
    assert pipeline["GemGiftBoxExchangeButton"]["expected"] == "^[兑兌][换換]$"
    assert pipeline["GemGiftBoxExchangeButton"]["roi"] == [789, 486, 169, 131]
    assert pipeline["GemGiftBoxConfirmButton"]["expected"] == "^确定$"
    assert pipeline["GemGiftBoxConfirmButton"]["roi"] == [557, 568, 178, 135]
    assert pipeline["GemGiftBoxRun"]["custom_action"] == "GemGiftBoxExchangeAllAction"
    assert business_next(pipeline["GemGiftBoxRun"]) == ["GemGiftBoxReturn"]
    assert business_next(pipeline["GemGiftBoxReturn"]) == ["GemGiftBoxVerifyTank"]


def test_card_click_uses_recipe_and_ok_midpoint():
    recipe_box = (55, 196, 108, 41)
    marker_box = (587, 195, 47, 35)
    assert my_action._gem_gift_box_card_click_point(recipe_box, marker_box) == (360, 215)


def test_interface_is_synchronized():
    paths = [
        ROOT / "assets/interface.json",
        ROOT / "client/interface.json",
        ROOT / "client_avalonia/interface.json",
    ]
    raw = [path.read_bytes() for path in paths]
    assert raw[0] == raw[1] == raw[2]
    interface = json.loads(raw[0].decode("utf-8"))
    assert any(task["entry"] == "GemGiftBoxTask" for task in interface["task"])


class Result:
    def __init__(self, hit=False, box=None):
        self.hit = hit
        self.box = box


class Job:
    def __init__(self, value=None):
        self.value = value

    def wait(self):
        return self

    def get(self):
        return self.value


class Controller:
    def __init__(self, completed=None, partial_levels=None, failure_mode=None):
        self.state = "page"
        self.viewport = "top"
        self.completed = set(completed) if completed is not None else {21, 41}
        self.partial_levels = set(partial_levels or [])
        self.failure_mode = failure_mode
        self.pending_level = None
        self.current_level = None
        self.clicks = []
        self.swipes = []
        self.plus_clicks = 0

    def post_screencap(self):
        return Job(np.zeros((720, 1280, 3), dtype=np.uint8))

    def post_swipe(self, x1, y1, x2, y2, duration):
        self.swipes.append((x1, y1, x2, y2, duration))
        self.viewport = "top" if y2 > y1 else "bottom"
        return Job()

    def post_click(self, x, y):
        self.clicks.append((x, y))
        if self.state == "page" and self.pending_level is not None:
            self.current_level = self.pending_level
            self.pending_level = None
            if self.failure_mode != "dialog_missing":
                self.state = "dialog"
        elif self.state == "dialog" and y < 480:
            self.plus_clicks += 1
        elif self.state == "dialog":
            if self.failure_mode != "confirm_missing":
                self.state = "confirm"
        elif self.state == "confirm":
            if self.failure_mode != "stuck_in_confirm":
                if self.current_level not in self.partial_levels:
                    self.completed.add(self.current_level)
                self.current_level = None
                self.state = "page"
        return Job()


class Context:
    TOP_BOXES = {
        16: (55, 196, 108, 41),
        21: (675, 196, 108, 41),
        26: (55, 386, 108, 41),
        31: (675, 386, 108, 41),
        36: (55, 576, 108, 41),
        41: (675, 576, 108, 41),
    }
    BOTTOM_BOXES = {
        36: (55, 280, 108, 41),
        41: (675, 280, 108, 41),
        46: (55, 500, 108, 41),
    }

    def __init__(self, completed=None, no_ok_levels=None, partial_levels=None, failure_mode=None):
        self.controller = Controller(
            completed=completed,
            partial_levels=partial_levels,
            failure_mode=failure_mode,
        )
        self.no_ok_levels = set(no_ok_levels or [])
        self.tasker = SimpleNamespace(
            controller=self.controller,
            running=True,
            stopping=False,
        )
        self.active_recipe = None

    def run_recognition(self, node_name, frame, pipeline_override=None):
        override = (pipeline_override or {}).get(node_name, {})
        ctrl = self.controller
        if node_name == "GemGiftBoxRun":
            return Result(ctrl.state == "page", (20, 90, 250, 40))
        if node_name == "GemGiftBoxTopRecipe":
            return Result(ctrl.state == "page" and ctrl.viewport == "top", (55, 196, 108, 41))
        if node_name == "GemGiftBoxRecipeLabel":
            level = int(override["expected"].split("级", 1)[0])
            boxes = self.TOP_BOXES if ctrl.viewport == "top" else self.BOTTOM_BOXES
            box = boxes.get(level)
            if ctrl.state == "page" and box is not None:
                self.active_recipe = level
                return Result(True, box)
            return Result()
        if node_name == "GemGiftBoxCompletedCount":
            if ctrl.state == "page" and self.active_recipe in ctrl.completed:
                return Result(True, (100, 330, 180, 30))
            return Result()
        if node_name == "GemGiftBoxExchangeableMarker":
            if (
                ctrl.state == "page"
                and self.active_recipe not in ctrl.completed
                and self.active_recipe not in self.no_ok_levels
            ):
                roi = override["roi"]
                ctrl.pending_level = self.active_recipe
                return Result(True, (roi[0] + 3, roi[1] + 2, 40, 30))
            return Result()
        if node_name == "GemGiftBoxExchangeDialog":
            return Result(ctrl.state == "dialog", (800, 250, 100, 80))
        if node_name == "GemGiftBoxPlusButton":
            return Result(ctrl.state == "dialog", (900, 370, 40, 40))
        if node_name == "GemGiftBoxExchangeButton":
            return Result(ctrl.state == "dialog", (820, 520, 80, 40))
        if node_name == "GemGiftBoxConfirmButton":
            return Result(ctrl.state == "confirm", (600, 600, 80, 40))
        return Result()


def test_all_seven_recipes_are_identity_driven_and_not_repeated():
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context()
        context.controller.viewport = "bottom"
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is True
    finally:
        my_action.time.sleep = original_sleep

    assert context.controller.completed == set(my_action.GEM_GIFT_BOX_LEVELS)
    # 21级和41级启动时已是 10/10，即使 OK 仍可存在也不会进入弹窗。
    assert context.controller.plus_clicks == 5 * 9
    assert any(y2 > y1 for _, y1, _, y2, _ in context.controller.swipes)
    assert any(y1 > y2 for _, y1, _, y2, _ in context.controller.swipes)


def test_scenario_a_missing_ok_on_first_recipe_does_not_abort_subsequent():
    """场景 A：16级未满但无 OK，后续配方正常兑换。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed={21, 41}, no_ok_levels={16})
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is True
    finally:
        my_action.time.sleep = original_sleep

    # 16 未兑换；21、41 先前已满；26、31、36、46 新完成兑换
    assert 16 not in context.controller.completed
    assert context.controller.completed == {21, 26, 31, 36, 41, 46}
    # 16 级未产生卡片点击 (360, 215)
    assert (360, 215) not in context.controller.clicks
    # 4 个新兑换项，每个 9 次加号
    assert context.controller.plus_clicks == 4 * 9


def test_scenario_b_missing_ok_on_middle_recipe_skips_cleanly():
    """场景 B：中间等级（31级）无 OK，其余正常兑换。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed=set(), no_ok_levels={31})
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is True
    finally:
        my_action.time.sleep = original_sleep

    assert 31 not in context.controller.completed
    assert context.controller.completed == {16, 21, 26, 36, 41, 46}
    assert context.controller.plus_clicks == 6 * 9


def test_scenario_c_multiple_missing_ok_recipes_complete_cleanly():
    """场景 C：多个等级（16、26、46）无 OK，其余等级正常兑换。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed=set(), no_ok_levels={16, 26, 46})
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is True
    finally:
        my_action.time.sleep = original_sleep

    assert context.controller.completed == {21, 31, 36, 41}
    assert not ({16, 26, 46} & context.controller.completed)
    assert context.controller.plus_clicks == 4 * 9


def test_exchange_button_regex_traditional_and_simplified():
    """测试 A：兑换按钮繁简字形兼容与误匹配防御。"""
    import re
    pattern = "^[兑兌][换換]$"
    # 正向匹配：支持简体、繁体及异体混合
    for valid_text in ["兑换", "兌換", "兑換", "兌换"]:
        assert re.match(pattern, valid_text) is not None, f"Should match {valid_text}"

    # 负向匹配：严格整词，绝不误伤计数或含上下文的文本
    for invalid_text in [
        "今日已兑换0/10",
        "今日已兌換0/10",
        "今日已兑换5/10",
        "兑换10/10",
        "兌換10/10",
        "去兑换",
        "兑换中",
        "兑",
        "换",
        "兌",
        "換",
    ]:
        assert re.match(pattern, invalid_text) is None, f"Should NOT match {invalid_text}"


def test_gem_gift_box_card_roi_right_column():
    """测试 B：右列 OK ROI 充分覆盖实机图标坐标，左列保持基准。"""
    # 右列 21 级配方 (x=675)
    recipe_box_21 = (675, 196, 108, 41)
    marker_roi_right = my_action._gem_gift_box_card_roi(recipe_box_21, "marker")
    # 左边界 <= 1199（实机 OK 起始约 1199，旧代码 1207 会切断左侧）
    assert marker_roi_right[0] <= 1199, f"Left bound {marker_roi_right[0]} must be <= 1199"
    # 右边界 >= 1239（实机 OK 宽度 40，1199 + 40 = 1239）
    assert marker_roi_right[0] + marker_roi_right[2] >= 1239, "Right bound must contain OK marker"
    assert marker_roi_right[2] >= 40
    assert marker_roi_right[1] == 196 - 25

    # 左列 16 级配方保持基准
    recipe_box_16 = (55, 196, 108, 41)
    marker_roi_left = my_action._gem_gift_box_card_roi(recipe_box_16, "marker")
    assert marker_roi_left[0] == 587
    assert marker_roi_left[2] == 47


def test_scenario_d_left_right_columns_with_skip_and_exchange():
    """测试 C：左右列完整流程（16级未满无OK跳过，21级右列OK兑换，26级左列OK兑换）。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed={31, 36, 41, 46}, no_ok_levels={16})
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is True
    finally:
        my_action.time.sleep = original_sleep

    # 16 级被跳过，不产生卡片点击
    assert 16 not in context.controller.completed
    assert (360, 215) not in context.controller.clicks
    # 21 级（右列）必须进入兑换并完成
    assert 21 in context.controller.completed
    # 26 级（左列）正常进入兑换并完成
    assert 26 in context.controller.completed
    # 2 个新兑换项，加号点击 2 * 9 = 18 次
    assert context.controller.plus_clicks == 2 * 9


def test_scenario_e_partial_exchange_continues_to_subsequent_recipes():
    """测试 E：部分兑换（如21级受材料限制只兑换部分未满10/10），记录并继续后续配方，不Abort。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        # 16级材料不足无OK；21级部分兑换；41级先前已满；26、31、36、46正常兑满
        context = Context(completed={41}, no_ok_levels={16}, partial_levels={21})
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is True
    finally:
        my_action.time.sleep = original_sleep

    # 16 未兑换且未点击卡片
    assert 16 not in context.controller.completed
    assert (360, 215) not in context.controller.clicks
    # 21 级执行了兑换事务（点击卡片、加号9次、确定），但未达成10/10，故不在 completed 中
    assert 21 not in context.controller.completed
    # 26, 31, 36, 46 均正常完成兑换（加上此前已满的 41）
    assert context.controller.completed == {26, 31, 36, 41, 46}
    # 5 个进入兑换弹窗的配方（21, 26, 31, 36, 46），每个点击加号 9 次
    assert context.controller.plus_clicks == 5 * 9


def test_transaction_failure_aborts_dialog_missing():
    """防御测试 1：配方卡片点击后兑换弹窗未打开，必须安全 Abort 返回 False。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed=set(), failure_mode="dialog_missing")
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is False
    finally:
        my_action.time.sleep = original_sleep


def test_transaction_failure_aborts_confirm_missing():
    """防御测试 2：点击兑换后结果确定按钮未出现，必须安全 Abort 返回 False。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed=set(), failure_mode="confirm_missing")
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is False
    finally:
        my_action.time.sleep = original_sleep


def test_transaction_failure_aborts_stuck_in_confirm():
    """防御测试 3：点击确定后未能返回兑换列表页面，必须安全 Abort 返回 False。"""
    original_sleep = my_action.time.sleep
    my_action.time.sleep = lambda _: None
    try:
        context = Context(completed=set(), failure_mode="stuck_in_confirm")
        action = my_action.GemGiftBoxExchangeAllAction()
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is False
    finally:
        my_action.time.sleep = original_sleep


if __name__ == "__main__":
    test_pipeline_contract()
    test_card_click_uses_recipe_and_ok_midpoint()
    test_interface_is_synchronized()
    test_all_seven_recipes_are_identity_driven_and_not_repeated()
    test_scenario_a_missing_ok_on_first_recipe_does_not_abort_subsequent()
    test_scenario_b_missing_ok_on_middle_recipe_skips_cleanly()
    test_scenario_c_multiple_missing_ok_recipes_complete_cleanly()
    test_exchange_button_regex_traditional_and_simplified()
    test_gem_gift_box_card_roi_right_column()
    test_scenario_d_left_right_columns_with_skip_and_exchange()
    test_scenario_e_partial_exchange_continues_to_subsequent_recipes()
    test_transaction_failure_aborts_dialog_missing()
    test_transaction_failure_aborts_confirm_missing()
    test_transaction_failure_aborts_stuck_in_confirm()
    print("[PASS] 宝石礼盒七配方身份、10/10 防重、部分兑换、无OK跳过与防御异常全场景闭环验证通过")

