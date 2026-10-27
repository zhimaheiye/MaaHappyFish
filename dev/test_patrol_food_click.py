"""Patrol feeding: missed click, fresh-frame retry and verified completion without a device."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action
from agent.starfish_food import pick_starfish_food


class FeedingContext:
    def __init__(self, close_on=1, final_state="panel"):
        self.state = "popup"
        self.close_on = close_on
        self.final_state = final_state
        self.clicks = []
        self.tasker = SimpleNamespace(controller=self, running=True, stopping=False)
        self.stop_after_click = False
        self.click_succeeds = True
        self.recognition_fails = False
        self.changed_food = False
        self.food_missing = False
        self.delay_confirmation = False

    def post_click(self, x, y):
        self.clicks.append((x, y))
        if self.close_on and len(self.clicks) >= self.close_on:
            self.state = self.final_state
        if self.stop_after_click:
            self.tasker.stopping = True
        return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=self.click_succeeds))

    def run_recognition(self, name, frame):
        if self.recognition_fails:
            return None
        return SimpleNamespace(hit=frame == ("popup" if name == "PatrolFoodPopupStillOpen" else "panel"))

    def pick(self, frame):
        if self.food_missing:
            return None
        name = "普通鱼食" if self.changed_food and self.clicks else "廉价鱼食"
        # Different boxes on retry ensure the action cannot reuse its first coordinates.
        return name, (644 + len(self.clicks) * 4, 173, 62, 43)


class PatrolFoodClickTests(unittest.TestCase):
    def run_action(self, context, param=None):
        clock = SimpleNamespace(now=0.0)
        def sleep(seconds): clock.now += seconds
        def capture(ctrl):
            if ctrl.delay_confirmation and ctrl.clicks and clock.now < 2.0:
                return "popup"
            return ctrl.state
        with patch.object(my_action, "_capture_720p", side_effect=capture), \
                patch.object(my_action, "pick_starfish_food", side_effect=context.pick), \
                patch.object(my_action.time, "monotonic", side_effect=lambda: clock.now), \
                patch.object(my_action.time, "sleep", side_effect=sleep):
            return my_action.FeedPatrolStarfishFoodAction().run(context, SimpleNamespace(
                custom_action_param=json.dumps(param if param is not None else {
                    "panel_node": "PatrolBrightReplenishPageIdentity"})))

    def test_first_click_closes_and_confirms_target(self):
        context = FeedingContext()
        self.assertTrue(self.run_action(context))
        self.assertEqual(context.clicks, [(675, 194)])

    def test_missed_click_retries_once_with_new_recognized_box(self):
        context = FeedingContext(close_on=2)
        self.assertTrue(self.run_action(context))
        self.assertEqual(context.clicks, [(675, 194), (679, 194)])

    def test_delayed_closure_waits_without_second_click(self):
        context = FeedingContext()
        context.delay_confirmation = True
        self.assertTrue(self.run_action(context))
        self.assertEqual(len(context.clicks), 1)

    def test_two_missed_clicks_fail_without_third(self):
        context = FeedingContext(close_on=None)
        self.assertFalse(self.run_action(context))
        self.assertEqual(len(context.clicks), 2)

    def test_wrong_page_after_closure_does_not_retry_or_report_success(self):
        context = FeedingContext(final_state="unknown")
        self.assertFalse(self.run_action(context))
        self.assertEqual(len(context.clicks), 1)

    def test_changed_food_not_substituted_on_retry(self):
        context = FeedingContext(close_on=None)
        context.changed_food = True
        self.assertFalse(self.run_action(context))
        self.assertEqual(len(context.clicks), 1)

    def test_missing_food_never_clicks(self):
        context = FeedingContext()
        context.food_missing = True
        self.assertFalse(self.run_action(context))
        self.assertEqual(context.clicks, [])

    def test_missing_popup_recognition_never_clicks(self):
        context = FeedingContext()
        context.recognition_fails = True
        self.assertFalse(self.run_action(context))
        self.assertEqual(context.clicks, [])

    def test_stopped_before_click(self):
        context = FeedingContext()
        context.tasker.stopping = True
        self.assertFalse(self.run_action(context))
        self.assertEqual(context.clicks, [])

    def test_stopped_after_click_does_not_report_success_or_retry(self):
        context = FeedingContext(close_on=None)
        context.stop_after_click = True
        self.assertFalse(self.run_action(context))
        self.assertEqual(len(context.clicks), 1)

    def test_click_failure_propagates(self):
        context = FeedingContext()
        context.click_succeeds = False
        self.assertFalse(self.run_action(context))
        self.assertEqual(len(context.clicks), 1)

    def test_unknown_target_panel_never_clicks(self):
        context = FeedingContext()
        self.assertFalse(self.run_action(context, {}))
        self.assertEqual(context.clicks, [])

    def test_failure_frame_still_identifies_the_same_cheap_upper_bag(self):
        path = ROOT / "dev/fixtures/patrol/food_click_20261025/bright_popup_still_open.png"
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(pick_starfish_food(frame), ("廉价鱼食", (644, 173, 62, 43)))


if __name__ == "__main__":
    unittest.main()
