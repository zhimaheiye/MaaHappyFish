"""Native fixed-frame regressions for the 2026-10-03 phone failures; no device."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
from maa.controller import CustomController
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action
from agent.runtime_state import mobile_ad_state

Library.open(Library.framework_libpath.parent, agent_server=False)
FIXTURES = ROOT / "dev/fixtures/mobile_ads_20261003"


class FrameController(CustomController):
    def __init__(self, frame):
        self.frame = frame
        self.clicks = []
        super().__init__()

    def connect(self):
        return True

    def request_uuid(self):
        return "offline-mobile-ad"

    def get_features(self):
        return 0

    def screencap(self):
        return self.frame.copy()

    def click(self, x, y):
        self.clicks.append((x, y))
        return True


class MobileAdCapsuleRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resource = Resource()
        assert cls.resource.post_bundle(ROOT / "assets/resource").wait().succeeded
        class FailProbe(my_action.FailTaskAction):
            calls = 0

            def run(self, context, argv):
                self.calls += 1
                return super().run(context, argv)
        cls.fail_probe = FailProbe()
        cls.resource.register_custom_action("FailTaskAction", cls.fail_probe)
        cls.pipeline = json.loads((ROOT / "assets/resource/pipeline/features/mobile_ads.json").read_text(encoding="utf-8"))

    def run_frame(self, path, node):
        frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        controller = FrameController(frame)
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(self.resource, controller))
        overrides = {"Probe": {"recognition": "DirectHit", "timeout": 100,
                               "rate_limit": 20, "next": [node]}}
        if node in ("MobileAdRewardedCapsule", "MobileAdDownloadEndcard"):
            overrides[node] = {"action": "Click", "next": [], "post_delay": 0}
        result = tasker.post_task("Probe", overrides).wait()
        return result.succeeded, controller.clicks

    def test_rewarded_capsule_clicks_real_cross_in_four_failed_ads(self):
        frames = [FIXTURES / "rewarded_capsule_live.png"]
        frames += [p for p in FIXTURES.glob("*MobileAdPlaying.png") if "20.49" not in p.name]
        self.assertEqual(len(frames), 5)
        for frame in frames:
            with self.subTest(frame=frame.name):
                success, clicks = self.run_frame(frame, "MobileAdRewardedCapsule")
                self.assertTrue(success)
                self.assertEqual(len(clicks), 1)
                x, y = clicks[0]
                self.assertTrue(1492 <= x <= 1524 and 44 <= y <= 76, clicks)

    def test_same_cross_during_countdown_and_game_pages_never_clicked(self):
        for name in ("playing_capsule_live.png", "reward_popup_live.png",
                     "2026.10.03-20.43.16.318_MobileAdCenter.png"):
            with self.subTest(frame=name):
                success, clicks = self.run_frame(FIXTURES / name, "MobileAdRewardedCapsule")
                self.assertFalse(success)
                self.assertEqual(clicks, [])

    def test_system_time_limit_is_native_failure_without_click(self):
        calls = self.fail_probe.calls
        success, clicks = self.run_frame(FIXTURES / "2026.10.03-20.49.41.48_MobileAdPlaying.png", "MobileAdDeviceTimeLimit")
        self.assertFalse(success)
        self.assertEqual(self.fail_probe.calls, calls + 1)
        self.assertEqual(clicks, [])

    def test_all_ad_waits_accept_rewarded_capsule_and_system_limit(self):
        for name in ("MobileAdRouter", "MobileAdCenter", "MobileAdCenterByOCR",
                     "MobileAdPlaying", "MobileAdPlayingByOCR", "MobileAdClickContinueCheck"):
            self.assertIn("MobileAdRewardedCapsule", self.pipeline[name]["next"])
            self.assertIn("MobileAdDownloadEndcard", self.pipeline[name]["next"])
            self.assertIn("MobileAdDeviceTimeLimit", self.pipeline[name]["next"])
        close = self.pipeline["MobileAdCloseRewardedCapsule"]
        self.assertEqual(close["all_of"], ["MobileAdRewardedText", "MobileAdCapsuleCloseIdentity"])
        self.assertEqual(close["box_index"], 1)
        self.assertNotIn("target", close)

    def test_download_overlay_clicks_only_real_cross_and_rejects_other_pages(self):
        success, clicks = self.run_frame(FIXTURES / "download_endcard_live.png", "MobileAdDownloadEndcard")
        self.assertTrue(success)
        self.assertEqual(len(clicks), 1)
        x, y = clicks[0]
        self.assertTrue(1532 <= x <= 1564 and 36 <= y <= 68, clicks)
        for name in ("playing_capsule_live.png", "rewarded_capsule_live.png", "reward_popup_live.png"):
            with self.subTest(frame=name):
                success, clicks = self.run_frame(FIXTURES / name, "MobileAdDownloadEndcard")
                self.assertFalse(success)
                self.assertEqual(clicks, [])
        self.assertIn("MobileAdDownloadEndcard", self.pipeline["MobileAdRewardedCapsule"]["next"])
        close = self.pipeline["MobileAdCloseDownloadEndcard"]
        self.assertEqual(close["all_of"], ["MobileAdDownloadText", "MobileAdDownloadCloseIdentity"])
        self.assertEqual(close["box_index"], 1)
        self.assertNotIn("target", close)

    def test_native_auto_transition_from_rewarded_capsule_to_download_overlay(self):
        load = lambda name: cv2.imdecode(np.fromfile(FIXTURES / name, dtype=np.uint8), 1)
        controller = FrameController(load("rewarded_capsule_live.png"))
        self.assertTrue(controller.post_connection().wait().succeeded)

        class SDKTransition(my_action.MobileAdOnAdStartAction):
            def run(self, context, argv):
                controller.frame = load("download_endcard_live.png")
                return super().run(context, argv)

        self.resource.register_custom_action("MobileAdOnAdStartAction", SDKTransition())
        self.resource.register_custom_action("ClickRecognizedCenterAction", my_action.ClickRecognizedCenterAction())
        tasker = Tasker()
        self.assertTrue(tasker.bind(self.resource, controller))
        override = {"MobileAdRouter": {"next": ["MobileAdRewardedCapsule"], "timeout": 100},
                    "MobileAdCloseDownloadEndcard": {"next": [], "post_delay": 0}}
        self.assertTrue(tasker.post_task("MobileAdRouter", override).wait().succeeded)
        self.assertEqual(controller.clicks, [(1548, 52)])

    def test_lobby_retry_is_bounded_preserves_count_and_resets_on_real_ad(self):
        context = MagicMock()
        args = SimpleNamespace(custom_action_param="null")
        my_action.MobileAdResetStateAction().run(context, args)
        mobile_ad_state.update(completed_cycles=7, reward_recorded=True)
        action = my_action.MobileAdRetryEntryAction()
        self.assertEqual([action.run(context, args) for _ in range(4)], [True, True, True, False])
        self.assertEqual(mobile_ad_state["completed_cycles"], 7)
        self.assertTrue(mobile_ad_state["reward_recorded"])
        my_action.MobileAdOnAdStartAction().run(context, args)
        self.assertEqual(mobile_ad_state["entry_retry_count"], 0)
        retry = self.pipeline["MobileAdRetryEntryFromCenter"]
        self.assertEqual(retry["all_of"], ["MobileAdCenter"])

    def test_native_lobby_retry_exhaustion_returns_failed_without_reward_reset(self):
        frame = cv2.imdecode(np.fromfile(FIXTURES / "2026.10.03-20.43.16.318_MobileAdCenter.png", dtype=np.uint8), 1)
        controller = FrameController(frame)
        self.assertTrue(controller.post_connection().wait().succeeded)
        self.resource.register_custom_action("MobileAdRetryEntryAction", my_action.MobileAdRetryEntryAction())
        tasker = Tasker()
        self.assertTrue(tasker.bind(self.resource, controller))
        mobile_ad_state.update(entry_retry_count=0, completed_cycles=7, reward_recorded=True)
        override = {name: {"action": "DoNothing", "post_delay": 0, "timeout": 100,
                           "next": ["MissingAd"]} for name in ("MobileAdCenter", "MobileAdCenterByOCR")}
        override["MissingAd"] = {"recognition": "OCR", "expected": "^no_ad$", "roi": [0, 0, 100, 100]}
        override["MobileAdRetryEntryFromCenter"] = {"post_delay": 0}
        self.assertTrue(tasker.post_task("MobileAdCenter", override).wait().failed)
        self.assertEqual(mobile_ad_state["entry_retry_count"], 3)
        self.assertEqual(mobile_ad_state["completed_cycles"], 7)
        self.assertTrue(mobile_ad_state["reward_recorded"])
        self.assertEqual(controller.clicks, [])


if __name__ == "__main__":
    unittest.main()
