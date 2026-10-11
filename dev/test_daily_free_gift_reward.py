"""每日免费礼包奖励弹窗：动画位置、点击确认和失败语义。"""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.my_action import DailyFreeGiftCloseRewardAction, FailTaskAction


class Controller:
    def __init__(self, frames, click_succeeds=True):
        self.frames = list(frames)
        self.last_frame = self.frames[-1]
        self.click_succeeds = click_succeeds
        self.clicks = []

    def capture(self):
        if self.frames:
            self.last_frame = self.frames.pop(0)
        return self.last_frame

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=self.click_succeeds))


class Context:
    def __init__(self, frames, click_succeeds=True):
        self.tasker = SimpleNamespace(
            controller=Controller(frames, click_succeeds), stopping=False, running=True
        )

    def run_recognition(self, name, frame):
        if name == "DailyFreeGiftRewardReturn":
            box = frame if isinstance(frame, tuple) else None
            hit = box is not None and 590 <= box[1] <= 640
            return SimpleNamespace(hit=hit, box=box if hit else None)
        if name == "DailyFreeGiftRechargePage":
            return SimpleNamespace(hit=frame == "page", box=(550, 55, 100, 30))
        raise AssertionError(name)


class DailyFreeGiftRewardTest(unittest.TestCase):
    def setUp(self):
        self.pipeline = json.loads(
            (ROOT / "assets/resource/pipeline/features/daily_free_gift.json").read_text(encoding="utf-8")
        )
        self.arg = SimpleNamespace(custom_action_param="null")

    def test_pipeline_waits_for_settled_reward_and_reports_real_failure(self):
        reward = self.pipeline["DailyFreeGiftRewardReturn"]
        self.assertEqual(reward["roi"], [600, 590, 80, 50])
        self.assertEqual(reward["custom_action"], "DailyFreeGiftCloseRewardAction")
        self.assertEqual(reward["next"][-1], "DailyFreeGiftExitRecharge")
        abort = self.pipeline["DailyFreeGiftAbort"]
        self.assertEqual(abort["custom_action"], "FailTaskAction")
        self.assertNotIn("next", abort)
        self.assertNotIn("on_error", abort)
        self.assertFalse(FailTaskAction().run(
            Context(["page"]), SimpleNamespace(custom_action_param=json.dumps(abort["custom_action_param"]))
        ))

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._capture_720p", side_effect=lambda controller: controller.capture())
    def test_animated_button_only_clicked_after_settling_and_page_confirmed(self, _capture, _sleep):
        context = Context([(620, 522, 37, 19), (620, 600, 37, 20),
                           (621, 601, 37, 20), "page", "page"])
        self.assertTrue(DailyFreeGiftCloseRewardAction().run(context, self.arg))
        self.assertEqual(context.tasker.controller.clicks, [(639, 611)])

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._capture_720p", side_effect=lambda controller: controller.capture())
    def test_stuck_popup_never_clicks_background_and_fails_bounded(self, _capture, _sleep):
        context = Context([(620, 602, 40, 20)])
        self.assertFalse(DailyFreeGiftCloseRewardAction().run(context, self.arg))
        self.assertEqual(context.tasker.controller.clicks, [(640, 612)] * 3)

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._capture_720p", side_effect=lambda controller: controller.capture())
    def test_early_animation_never_clicked(self, _capture, _sleep):
        context = Context([(620, 522, 37, 19)])
        self.assertFalse(DailyFreeGiftCloseRewardAction().run(context, self.arg))
        self.assertEqual(context.tasker.controller.clicks, [])

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._capture_720p", side_effect=lambda controller: controller.capture())
    def test_touch_failure_stops_immediately(self, _capture, _sleep):
        context = Context([(620, 602, 40, 20)], click_succeeds=False)
        self.assertFalse(DailyFreeGiftCloseRewardAction().run(context, self.arg))
        self.assertEqual(context.tasker.controller.clicks, [(640, 612)])


if __name__ == "__main__":
    unittest.main()
