import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import agent.runtime_state as runtime_state
from agent.my_action import (
    FeedManateeUntilExhaustedAction,
    InitFriendGemStateAction,
    InitManateeStateAction,
)
from agent.my_reco import CheckManateeStateReco


PIPELINE_DIR = os.path.join(ROOT, "assets", "resource", "pipeline", "features")
IMAGE_DIR = os.path.join(ROOT, "assets", "resource", "image")


class _Job:
    def __init__(self, value=None):
        self.value = value

    def wait(self):
        return self

    def get(self):
        return self.value


class _Controller:
    def __init__(self):
        self.clicks = []
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    def post_screencap(self):
        return _Job(self.frame)

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return _Job()


class _Context:
    def __init__(self, exhausted_after=30, tank_visible=True):
        self.tasker = SimpleNamespace(
            controller=_Controller(), stopping=False, running=True
        )
        self.exhausted_after = exhausted_after
        self.tank_visible = tank_visible

    def run_recognition(self, name, _frame):
        if name == "ManateeExhausted":
            hit = len(self.tasker.controller.clicks) >= self.exhausted_after
        elif name == "ManateeTankIdentity":
            hit = self.tank_visible
        else:
            hit = False
        return SimpleNamespace(hit=hit, box=(1, 1, 10, 10))


class ManateePipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PIPELINE_DIR, "manatee.json"), encoding="utf-8") as f:
            cls.manatee = json.load(f)
        with open(os.path.join(PIPELINE_DIR, "friend_gem.json"), encoding="utf-8") as f:
            cls.friend_gem = json.load(f)

    def test_user_assets_and_rois_are_wired_exactly(self):
        expected = {
            "ManateeOpenFriendPage": ("好友页面_入口.png", [1128, 205, 131, 124]),
            "ManateeOpenFeed": ("好友_喂食.png", [1126, 258, 143, 145]),
            "ManateeSelectFood": ("海牛先生_选择喂食.png", [795, 265, 159, 135]),
        }
        for node_name, (template, roi) in expected.items():
            node = self.manatee[node_name]
            self.assertEqual(node["template"], template)
            self.assertEqual(node["roi"], roi)
            self.assertEqual(node["action"], "Click")
            self.assertTrue(os.path.isfile(os.path.join(IMAGE_DIR, template)))

        select_manatee = self.manatee["ManateeStartFromFriendList"]
        self.assertEqual(select_manatee["expected"], "海牛先生")
        self.assertEqual(select_manatee["roi"], [460, 185, 183, 127])
        exhausted = self.manatee["ManateeExhausted"]
        self.assertEqual(exhausted["expected"], "刷新体力")
        self.assertEqual(exhausted["roi"], [0, 70, 327, 244])
        tank_next = self.manatee["ManateeTankIdentity"]["next"]
        self.assertLess(
            tank_next.index("ManateeExhausted"), tank_next.index("ManateeOpenFeed")
        )
        self.assertIn("ManateeReturnStandalone", exhausted["next"])
        self.assertIn("ManateeReturnFriendGem", exhausted["next"])

    def test_friend_gem_enters_from_tank_and_runs_manatee_before_next_friend(self):
        start_next = self.friend_gem["FriendGemStartRouter"]["next"]
        self.assertNotIn("ManateeStartFromFriendList", start_next)
        self.assertIn("FriendGemStartFromFriendList", start_next)
        self.assertIn(
            "FriendGemFriendRouter",
            self.friend_gem["FriendGemStartFromFriendList"]["next"],
        )
        entry = self.friend_gem["FriendGemOpenFriendPage"]
        self.assertEqual(entry["template"], "好友页面_入口.png")
        self.assertEqual(entry["roi"], [1128, 205, 131, 124])
        self.assertEqual(entry["action"], "Click")
        self.assertIn("FriendGemStartRouter", entry["next"])
        self.assertIn(
            "ManateeTankIdentity",
            self.friend_gem["FriendGemCheckManatee"]["next"],
        )
        self.assertIn(
            "FriendGemNextFriend", self.manatee["ManateeReturnFriendGem"]["next"]
        )

    def test_standalone_returns_twice_and_verifies_each_page(self):
        self.assertIn(
            "ManateeBackToFriendList",
            self.manatee["ManateeReturnStandalone"]["next"],
        )
        self.assertIn(
            "ManateeVerifyFriendList",
            self.manatee["ManateeBackToFriendList"]["next"],
        )
        self.assertIn(
            "ManateeBackToTank",
            self.manatee["ManateeVerifyFriendList"]["next"],
        )
        self.assertIn(
            "ManateeVerifyMainTank", self.manatee["ManateeBackToTank"]["next"]
        )

    def test_feed_clicks_at_least_30_until_exhausted(self):
        init = InitManateeStateAction()
        init.run(None, SimpleNamespace(custom_action_param={"return_mode": "standalone"}))
        self.assertEqual(runtime_state.manatee_state["return_mode"], "standalone")

        context = _Context(exhausted_after=30)
        argv = SimpleNamespace(
            custom_action_param={"min_clicks": 30, "max_clicks": 120}
        )
        with patch("agent.my_action.time.sleep", return_value=None):
            result = FeedManateeUntilExhaustedAction().run(context, argv)
        self.assertTrue(result)
        self.assertEqual(len(context.tasker.controller.clicks), 30)
        for x, y in context.tasker.controller.clicks:
            self.assertTrue(792 <= x < 1133)
            self.assertTrue(288 <= y < 643)

    def test_feed_stops_before_click_when_page_gate_is_missing(self):
        context = _Context(exhausted_after=30, tank_visible=False)
        argv = SimpleNamespace(
            custom_action_param={"min_clicks": 30, "max_clicks": 120}
        )
        result = FeedManateeUntilExhaustedAction().run(context, argv)
        self.assertFalse(result)
        self.assertEqual(context.tasker.controller.clicks, [])

    def test_feed_stops_immediately_when_task_is_cancelled(self):
        context = _Context(exhausted_after=30)
        context.tasker.stopping = True
        argv = SimpleNamespace(
            custom_action_param={"min_clicks": 30, "max_clicks": 120}
        )
        result = FeedManateeUntilExhaustedAction().run(context, argv)
        self.assertFalse(result)
        self.assertEqual(context.tasker.controller.clicks, [])

    def test_friend_gem_initialization_selects_friend_return_mode(self):
        InitFriendGemStateAction().run(None, None)
        self.assertEqual(runtime_state.manatee_state["return_mode"], "friend_gem")
        self.assertEqual(runtime_state.manatee_state["last_feed_count"], 0)

    def test_mode_recognition_uses_shared_state(self):
        reco = CheckManateeStateReco()
        runtime_state.manatee_state["return_mode"] = "friend_gem"
        friend_argv = SimpleNamespace(
            custom_recognition_param={"condition": "friend_gem"}
        )
        standalone_argv = SimpleNamespace(
            custom_recognition_param={"condition": "standalone"}
        )
        self.assertIsNotNone(reco.analyze(None, friend_argv))
        self.assertIsNone(reco.analyze(None, standalone_argv))


if __name__ == "__main__":
    unittest.main()
