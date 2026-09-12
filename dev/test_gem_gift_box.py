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
    assert pipeline["GemGiftBoxExchangeButton"]["expected"] == "^兑换$"
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
    def __init__(self):
        self.state = "page"
        self.viewport = "top"
        self.completed = {21, 41}
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
            self.state = "dialog"
        elif self.state == "dialog" and y < 480:
            self.plus_clicks += 1
        elif self.state == "dialog":
            self.state = "confirm"
        elif self.state == "confirm":
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

    def __init__(self):
        self.controller = Controller()
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
            if ctrl.state == "page" and self.active_recipe not in ctrl.completed:
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


if __name__ == "__main__":
    test_pipeline_contract()
    test_card_click_uses_recipe_and_ok_midpoint()
    test_interface_is_synchronized()
    test_all_seven_recipes_are_identity_driven_and_not_repeated()
    print("[PASS] 宝石礼盒七配方身份、10/10 防重、滚动与兑换闭环验证通过")
