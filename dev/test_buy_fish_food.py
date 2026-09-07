import json
import os
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent.my_action as actions


class Job:
    def __init__(self, value=None):
        self.value = value

    def wait(self):
        return self

    def get(self):
        return self.value


class Controller:
    def __init__(self, state="detail"):
        self.state = state
        self.quantity = 1
        self.clicks = []
        self.swipes = []
        self.on_click = None

    def post_screencap(self):
        return Job(np.zeros((720, 1280, 3), dtype=np.uint8))

    def post_click(self, x, y):
        self.clicks.append((x, y))
        if self.on_click is not None:
            self.on_click(x, y)
        if (x, y) == (110, 110):
            self.quantity += 1
        elif (x, y) == (320, 320):
            self.state = "detail"
        elif (x, y) == (210, 210):
            self.state = "store"
        elif (x, y) == (20, 20):
            self.state = "tank"
        return Job()

    def post_swipe(self, *args):
        self.swipes.append(args)
        return Job()


class Context:
    def __init__(self, state="detail", target_visible=True, initial_quantity_text=None):
        self.tasker = SimpleNamespace(controller=Controller(state), running=True, stopping=False)
        self.target_visible = target_visible
        self.initial_quantity_text = initial_quantity_text
        self.long_presses = []
        self.stop_after_long_press = False

    def run_recognition(self, node_name, _frame):
        state = self.tasker.controller.state
        boxes = {
            "detail": {
                "BuyFishFoodDetailIdentity": (50, 50, 20, 20),
                "BuyFishFoodUnitPrice": (70, 70, 20, 20),
                "BuyFishFoodPlusButton": (100, 100, 20, 20),
                "BuyFishFoodQuantity": (150, 150, 20, 20),
                "BuyFishFoodPurchaseButton": (200, 200, 20, 20),
            },
            "store": {
                "BuyFishFoodStoreIdentity": (10, 10, 20, 20),
                "BuyFishFoodStoreItemIdentity": (40, 40, 20, 20),
                "BuyFishFoodTargetCard": (300, 300, 40, 40),
            },
            "tank": {
                "BuyFishFoodTankIdentity": (1, 1, 20, 20),
            },
        }
        box = boxes.get(state, {}).get(node_name)
        if node_name == "BuyFishFoodTargetCard" and not self.target_visible:
            box = None
        best_result = None
        if node_name == "BuyFishFoodQuantity" and box is not None:
            text = str(self.tasker.controller.quantity)
            if self.initial_quantity_text is not None and self.tasker.controller.quantity == 1:
                text = self.initial_quantity_text
            best_result = SimpleNamespace(text=text)
        return SimpleNamespace(hit=box is not None, box=box or (0, 0, 0, 0), best_result=best_result)

    def run_action_direct(self, _action_type, action_param, box):
        self.long_presses.append((action_param.duration, box))
        self.tasker.controller.quantity += 6
        if self.stop_after_long_press:
            self.tasker.stopping = True
        return SimpleNamespace(success=True)


def run_tests():
    with open("assets/resource/pipeline/features/buy_fish_food.json", "r", encoding="utf-8") as file:
        pipeline = json.load(file)
    business_next = [
        name
        for name in pipeline["BuyFishFoodStartRouter"]["next"]
        if not name.startswith("[JumpBack]Global")
    ]
    assert business_next == [
        "BuyFishFoodStartAtDetail",
        "BuyFishFoodStartAtStore",
        "BuyFishFoodStartAtFeedPopup",
        "BuyFishFoodStartAtTank",
    ]
    assert "target" not in pipeline["BuyFishFoodOpenFeedPopup"]
    assert "target" not in pipeline["BuyFishFoodOpenStore"]
    assert pipeline["BuyFishFoodQuantity"]["only_rec"] is True
    assert "」" in pipeline["BuyFishFoodQuantity"]["expected"]

    original_sleep = actions.time.sleep
    actions.time.sleep = lambda _seconds: None
    try:
        purchase_context = Context("detail")
        purchase_arg = SimpleNamespace(custom_action_param={"bags": 3})
        assert actions.BuyCheapFishFoodAction().run(purchase_context, purchase_arg) is True
        assert purchase_context.tasker.controller.clicks == [
            (110, 110),
            (110, 110),
            (210, 210),
            (20, 20),
        ]
        assert purchase_context.tasker.controller.state == "tank"

        confused_one_context = Context("detail", initial_quantity_text="」")
        assert actions.BuyCheapFishFoodAction().run(confused_one_context, purchase_arg) is True
        assert confused_one_context.tasker.controller.quantity == 3

        stopped_context = Context("detail")
        stopped_context.tasker.controller.on_click = lambda x, y: setattr(
            stopped_context.tasker,
            "stopping",
            (x, y) == (110, 110),
        )
        stopped_arg = SimpleNamespace(custom_action_param={"bags": 10})
        assert actions.BuyCheapFishFoodAction().run(stopped_context, stopped_arg) is False
        assert stopped_context.tasker.controller.clicks == [(110, 110)]

        bulk_context = Context("detail")
        bulk_arg = SimpleNamespace(custom_action_param={"bags": 25})
        assert actions.BuyCheapFishFoodAction().run(bulk_context, bulk_arg) is True
        assert bulk_context.long_presses
        assert bulk_context.tasker.controller.quantity == 25

        stopped_hold_context = Context("detail")
        stopped_hold_context.stop_after_long_press = True
        assert actions.BuyCheapFishFoodAction().run(stopped_hold_context, bulk_arg) is False
        assert len(stopped_hold_context.long_presses) == 1
        assert stopped_hold_context.tasker.controller.clicks == []

        find_context = Context("store")
        find_arg = SimpleNamespace(custom_action_param={"max_scrolls": 2})
        assert actions.FindCheapFishFoodAction().run(find_context, find_arg) is True
        assert find_context.tasker.controller.clicks == [(320, 320)]

        missing_context = Context("store", target_visible=False)
        assert actions.FindCheapFishFoodAction().run(missing_context, find_arg) is False
        assert missing_context.tasker.controller.clicks == []
        assert len(missing_context.tasker.controller.swipes) == 2
    finally:
        actions.time.sleep = original_sleep

    print("[PASS] BuyFishFoodTask topology, recognized clicks, bounded search, and tank return")


if __name__ == "__main__":
    run_tests()
