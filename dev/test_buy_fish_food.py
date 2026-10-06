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
        self.on_swipe = None

    def post_screencap(self):
        return Job(np.zeros((720, 1280, 3), dtype=np.uint8))

    def post_click(self, x, y):
        self.clicks.append((x, y))
        override = self.on_click(x, y) if self.on_click is not None else None
        if isinstance(override, str):
            self.state = override
        elif (x, y) == (110, 110):
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
        if self.on_swipe is not None:
            self.on_swipe(len(self.swipes))
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
            "fish_store": {
                "BuyFishFoodStoreIdentity": (10, 10, 20, 20),
                "BuyFishFoodStoreItemIdentity": (40, 40, 20, 20),
                "BuyFishFoodTargetCard": (300, 300, 40, 40),
            },
            "last_store": {
                "BuyFishFoodStoreIdentity": (10, 10, 20, 20),
                "BuyFishFoodTargetCard": (300, 300, 40, 40),
            },
            "detail_back": {
                "BuyFishFoodStoreIdentity": (10, 10, 20, 20),
                "BuyFishFoodDetailIdentity": (50, 50, 20, 20),
                "BuyFishFoodUnitPrice": (70, 70, 20, 20),
                "BuyFishFoodTargetCard": (300, 300, 40, 40),
                "BuyFishFoodPlusButton": (100, 100, 20, 20),
                "BuyFishFoodQuantity": (150, 150, 20, 20),
                "BuyFishFoodPurchaseButton": (200, 200, 20, 20),
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
    assert "F" in pipeline["BuyFishFoodQuantity"]["expected"]
    assert pipeline["BuyFishFoodQuantity"]["roi"] == [892, 345, 125, 92]
    assert "雪花鱼食" in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]
    assert "粉光鱼食" in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]
    assert "珀光鱼食" in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]
    assert "廉价鱼食" not in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]
    assert pipeline["BuyFishFoodStartAtStore"]["custom_action_param"]["max_scrolls"] == 12
    assert pipeline["BuyFishFoodVerifyStore"]["custom_action_param"]["max_scrolls"] == 12
    assert pipeline["BuyFishFoodStartAtDetail"]["expected"] == "廉价鱼食|普通鱼食|高级鱼食"
    assert pipeline["BuyFishFoodDetailIdentity"]["expected"] == "廉价.*鱼食"
    assert pipeline["BuyFishFoodTargetNormal"]["expected"] == "^普通鱼食$"
    assert pipeline["BuyFishFoodTargetHigh"]["expected"] == "^高级鱼食$"
    assert pipeline["BuyFishFoodPriceNormal"]["expected"] == "^2000$"
    assert pipeline["BuyFishFoodPriceHigh"]["expected"] == "^8500$"
    assert pipeline["BuyFishFoodUnitPrice"]["expected"] == "^400$"
    assert "冰心鱼食" in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]
    assert "普通鱼食" not in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]
    assert "高级鱼食" not in pipeline["BuyFishFoodStoreItemIdentity"]["expected"]

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

        misread_f_context = Context("detail", initial_quantity_text="F")
        assert actions.BuyCheapFishFoodAction().run(misread_f_context, purchase_arg) is True
        assert misread_f_context.tasker.controller.quantity == 3

        other_letter_context = Context("detail", initial_quantity_text="A")
        assert actions.BuyCheapFishFoodAction().run(other_letter_context, purchase_arg) is False
        assert other_letter_context.tasker.controller.clicks == []

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

        # 现场：1 秒只增 5 袋、5 秒约增 92 袋，短段因启动延迟只增 7 袋。
        # 短段不能使后续长按从较短时长突然扩大至 5 秒。
        timed_context = Context("detail")
        hold_history = []
        def timed_hold(_action_type, action_param, box):
            duration = action_param.duration
            before = timed_context.tasker.controller.quantity
            gain = 5 if not hold_history else (92 if duration == 5000 else 7)
            hold_history.append((before, duration, gain))
            timed_context.tasker.controller.quantity += gain
            return SimpleNamespace(success=True)
        timed_context.run_action_direct = timed_hold
        assert actions.BuyCheapFishFoodAction().run(
            timed_context, SimpleNamespace(custom_action_param={"bags": 900})
        ) is True
        assert timed_context.tasker.controller.quantity == 900
        assert any(1000 < duration < 5000 for _, duration, _ in hold_history)
        for index, (before, duration, gain) in enumerate(hold_history):
            if index >= 2:
                assert duration * 18.4 / 1000 <= 900 - before - 20 + 0.01
            if index and hold_history[index - 1][1] < 5000:
                assert duration <= hold_history[index - 1][1] or index == 1

        overshoot_context = Context("detail")
        def excessive_hold(_action_type, action_param, box):
            overshoot_context.tasker.controller.quantity += 50
            return SimpleNamespace(success=True)
        overshoot_context.run_action_direct = excessive_hold
        assert actions.BuyCheapFishFoodAction().run(overshoot_context, bulk_arg) is False
        assert overshoot_context.tasker.controller.clicks == []

        missed_click_context = Context("detail")
        missed_click_context.tasker.controller.on_click = lambda x, y: "detail"
        assert actions.BuyCheapFishFoodAction().run(missed_click_context, purchase_arg) is False
        assert (210, 210) not in missed_click_context.tasker.controller.clicks

        capped_context = Context("detail")
        def capped_hold(_action_type, action_param, box):
            assert action_param.duration == 6000
            capped_context.tasker.controller.quantity = 999
            return SimpleNamespace(success=True)
        capped_context.run_action_direct = capped_hold
        assert actions.BuyCheapFishFoodAction().run(
            capped_context, SimpleNamespace(custom_action_param={"bags": 999})
        ) is True
        assert capped_context.tasker.controller.quantity == 999

        stopped_hold_context = Context("detail")
        stopped_hold_context.stop_after_long_press = True
        assert actions.BuyCheapFishFoodAction().run(stopped_hold_context, bulk_arg) is False
        assert len(stopped_hold_context.long_presses) == 1
        assert stopped_hold_context.tasker.controller.clicks == []

        find_context = Context("store")
        find_arg = SimpleNamespace(custom_action_param={"max_scrolls": 2})
        assert actions.FindCheapFishFoodAction().run(find_context, find_arg) is True
        assert find_context.tasker.controller.clicks == [(320, 320)]

        already_detail = Context("detail")
        assert actions.FindCheapFishFoodAction().run(already_detail, find_arg) is True
        assert already_detail.tasker.controller.clicks == []

        missing_context = Context("store", target_visible=False)
        assert actions.FindCheapFishFoodAction().run(missing_context, find_arg) is False
        assert missing_context.tasker.controller.clicks == []
        assert len(missing_context.tasker.controller.swipes) == 2

        recovery_context = Context("store", target_visible=False)
        def after_swipe(count):
            recovery_context.tasker.controller.state = "fish_store"
            recovery_context.target_visible = count >= 2
        recovery_context.tasker.controller.on_swipe = after_swipe
        assert actions.FindCheapFishFoodAction().run(
            recovery_context, SimpleNamespace(custom_action_param={"max_scrolls": 3})
        ) is True
        assert recovery_context.tasker.controller.swipes == [
            (640, 580, 640, 480, 500),
            (640, 580, 640, 480, 500),
        ]
        assert recovery_context.tasker.controller.clicks == [(320, 320)]

        last_card_context = Context("last_store")
        assert actions.FindCheapFishFoodAction().run(last_card_context, find_arg) is True
        assert last_card_context.tasker.controller.clicks == [(320, 320)]

        def purchase_lands(state):
            def on_click(x, y):
                if (x, y) == (210, 210):
                    return state
                return None
            return on_click

        one_bag = SimpleNamespace(custom_action_param={"bags": 1})
        last_return = Context("detail")
        last_return.tasker.controller.on_click = purchase_lands("last_store")
        assert actions.BuyCheapFishFoodAction().run(last_return, one_bag) is True
        assert last_return.tasker.controller.clicks == [(210, 210), (20, 20)]
        assert last_return.tasker.controller.state == "tank"

        stuck_detail = Context("detail")
        stuck_detail.tasker.controller.on_click = purchase_lands("detail_back")
        assert actions.BuyCheapFishFoodAction().run(stuck_detail, one_bag) is False
        assert stuck_detail.tasker.controller.clicks == [(210, 210)]
    finally:
        actions.time.sleep = original_sleep

    print("[PASS] BuyFishFoodTask topology, recognized clicks, bounded search, and tank return")


if __name__ == "__main__":
    run_tests()
