#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Offline unit test for full closed-loop ad cycle components and router state machine."""

import os
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.runtime_state import mobile_ad_state
from agent.my_action import (
    MobileAdResetStateAction,
    MobileAdRecordRewardAction,
    MobileAdOnAdStartAction,
)
from agent.my_reco import MobileAdCheckCycleLimitReco

from dev.run_mobile_ad_full_cycle_test import (
    check_reward_popup,
    check_wheel_stop_button,
    TPL_ENDCARD_X,
    TPL_CHECK_BTN,
    TPL_CAPSULE,
)

TPL_WATCH_BTN = "assets/resource/image/mobile_ads/看视频赚大奖_入口.png"
_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def simulate_pipeline_router(maa_img: np.ndarray) -> str:
    """Simulates MobileAdRouter dispatching logic exactly matching mobile_ads.json."""
    ocr = get_ocr()

    # 1. MobileAdVerifyRewardPopup
    roi_popup = maa_img[200:480, 600:1000]
    res_popup, _ = ocr(roi_popup)
    if res_popup:
        texts = [r[1] for r in res_popup]
        if any("恭喜你获得如下奖励" in t or "要继续观看下一段视频吗" in t or "继续观看下一段视频" in t for t in texts):
            return "MobileAdVerifyRewardPopup"

    # 2. MobileAdWheelStop (expected: ^停止$)
    roi_wheel = maa_img[480:620, 980:1140]
    res_wheel, _ = ocr(roi_wheel)
    if res_wheel:
        for item in res_wheel:
            t = item[1].strip()
            if re.search(r"^停止$", t):
                return "MobileAdWheelStop"

    # 3. MobileAdEndcard (template match >= 0.80)
    tpl_endcard = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_ENDCARD_X), dtype=np.uint8), cv2.IMREAD_COLOR)
    roi_endcard = maa_img[20:90, 1515:1590]
    res_e = cv2.matchTemplate(roi_endcard, tpl_endcard, cv2.TM_CCOEFF_NORMED)
    _, max_e, _, _ = cv2.minMaxLoc(res_e)
    if max_e >= 0.80:
        return "MobileAdEndcard"

    # 4. MobileAdPlaying (capsule match >= 0.65)
    tpl_capsule = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_CAPSULE), dtype=np.uint8), cv2.IMREAD_COLOR)
    roi_capsule = maa_img[10:90, 1350:1590]
    res_c = cv2.matchTemplate(roi_capsule, tpl_capsule, cv2.TM_CCOEFF_NORMED)
    _, max_c, _, _ = cv2.minMaxLoc(res_c)
    if max_c >= 0.65:
        return "MobileAdPlaying"

    # 5. MobileAdCenter (template match >= 0.80)
    tpl_watch = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_WATCH_BTN), dtype=np.uint8), cv2.IMREAD_COLOR)
    roi_center = maa_img[500:610, 990:1130]
    res_w = cv2.matchTemplate(roi_center, tpl_watch, cv2.TM_CCOEFF_NORMED)
    _, max_w, _, _ = cv2.minMaxLoc(res_w)
    if max_w >= 0.80:
        return "MobileAdCenter"

    return "Unknown"


class TestFullCycleAdComponents(unittest.TestCase):
    def setUp(self):
        self.evidence_dir = REPO_ROOT / "dev" / "evidence" / "mobile_ads_investigation"
        self.tpl_endcard = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_ENDCARD_X), dtype=np.uint8), cv2.IMREAD_COLOR)
        self.tpl_check = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_CHECK_BTN), dtype=np.uint8), cv2.IMREAD_COLOR)
        self.tpl_capsule = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_CAPSULE), dtype=np.uint8), cv2.IMREAD_COLOR)
        self.tpl_watch = cv2.imdecode(np.fromfile(str(REPO_ROOT / TPL_WATCH_BTN), dtype=np.uint8), cv2.IMREAD_COLOR)

    def test_case1_standard_lobby_routes_to_center(self):
        """Case 1: Ordinary 8/10 Ad Center lobby MUST route to MobileAdCenter, NEVER to WaitReturn or WheelStop."""
        lobby_path = self.evidence_dir / "current_phone_screen.png"
        raw = cv2.imread(str(lobby_path))
        maa_img = cv2.resize(raw, (1600, 720), interpolation=cv2.INTER_AREA)

        dest = simulate_pipeline_router(maa_img)
        self.assertEqual(dest, "MobileAdCenter", f"Lobby screen should route to MobileAdCenter, but got {dest}")
        self.assertNotEqual(dest, "MobileAdWaitReturn")
        self.assertNotEqual(dest, "MobileAdWheelStop")

    def test_case2_wheel_spinning_routes_to_wheel_stop(self):
        """Case 2: When wheel is spinning with '停止', router MUST route to MobileAdWheelStop."""
        f022_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "022.png"
        img = cv2.imread(str(f022_path))

        dest = simulate_pipeline_router(img)
        self.assertEqual(dest, "MobileAdWheelStop", f"Spinning wheel should route to MobileAdWheelStop, got {dest}")

    def test_case3_reward_popup_priority_routing(self):
        """Case 3: When reward popup is displayed, router MUST prioritize MobileAdVerifyRewardPopup."""
        f033_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "033.png"
        img = cv2.imread(str(f033_path))

        dest = simulate_pipeline_router(img)
        self.assertEqual(dest, "MobileAdVerifyRewardPopup", f"Reward popup should route to MobileAdVerifyRewardPopup, got {dest}")

    def test_case4_endcard_routing(self):
        """Case 4: When Endcard is reached, router MUST route to MobileAdEndcard."""
        f018_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "018.png"
        img = cv2.imread(str(f018_path))

        dest = simulate_pipeline_router(img)
        self.assertEqual(dest, "MobileAdEndcard", f"Endcard screen should route to MobileAdEndcard, got {dest}")

    def test_case5_playing_ad_not_endcard(self):
        """Case 5: Playing ad screen MUST NOT match Endcard; should route to MobileAdPlaying."""
        f004_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "004.png"
        img = cv2.imread(str(f004_path))

        # Check Endcard score directly
        roi_endcard = img[20:90, 1515:1590]
        res_e = cv2.matchTemplate(roi_endcard, self.tpl_endcard, cv2.TM_CCOEFF_NORMED)
        _, max_e, _, _ = cv2.minMaxLoc(res_e)
        self.assertLess(max_e, 0.30, f"Playing ad should not match Endcard X (got {max_e})")

        dest = simulate_pipeline_router(img)
        self.assertEqual(dest, "MobileAdPlaying", f"Playing ad should route to MobileAdPlaying, got {dest}")


class MockArg:
    def __init__(self, custom_param=None):
        self.custom_action_param = custom_param or {}
        self.custom_recognition_param = custom_param or {}
        self.image = None


class TestMobileAdRewardIdempotencyAndPureReco(unittest.TestCase):
    def setUp(self):
        mobile_ad_state["completed_cycles"] = 0
        mobile_ad_state["reward_recorded"] = False
        mobile_ad_state["max_cycles"] = 3
        self.context = MagicMock()
        self.reset_action = MobileAdResetStateAction()
        self.record_action = MobileAdRecordRewardAction()
        self.ad_start_action = MobileAdOnAdStartAction()
        self.check_reco = MobileAdCheckCycleLimitReco()

    def test_case1_same_popup_called_5_times_increments_only_once(self):
        """Case 1: 同一个奖励弹窗连续调用 5 次，completed_cycles 只 +1。"""
        self.reset_action.run(self.context, MockArg({"max_cycles": 10}))
        self.assertEqual(mobile_ad_state["completed_cycles"], 0)
        self.assertFalse(mobile_ad_state["reward_recorded"])

        for _ in range(5):
            res = self.record_action.run(self.context, MockArg())
            self.assertTrue(res)

        self.assertEqual(mobile_ad_state["completed_cycles"], 1, "Completed cycles must only increment once")
        self.assertTrue(mobile_ad_state["reward_recorded"])

    def test_case2_router_reentry_does_not_increment_if_already_recorded(self):
        """Case 2: reward_recorded=True 时 Router 再次进入奖励弹窗，不重复计数。"""
        mobile_ad_state["completed_cycles"] = 1
        mobile_ad_state["reward_recorded"] = True
        mobile_ad_state["max_cycles"] = 5

        res = self.record_action.run(self.context, MockArg())
        self.assertTrue(res)
        self.assertEqual(mobile_ad_state["completed_cycles"], 1, "Must not increment when reward_recorded is True")
        self.assertTrue(mobile_ad_state["reward_recorded"])

    def test_case3_ad_start_resets_reward_recorded(self):
        """Case 3: 确认下一广告启动后，reward_recorded 重置为 False。"""
        mobile_ad_state["completed_cycles"] = 1
        mobile_ad_state["reward_recorded"] = True

        res = self.ad_start_action.run(self.context, MockArg())
        self.assertTrue(res)
        self.assertFalse(mobile_ad_state["reward_recorded"], "Ad start action must reset reward_recorded to False")
        self.assertEqual(mobile_ad_state["completed_cycles"], 1, "Completed cycles remains 1 during ad playback")

    def test_case4_new_popup_increments_completed_cycles(self):
        """Case 4: 下一条广告完成，再进入新的奖励弹窗，completed_cycles 正常再 +1。"""
        # Cycle 1
        self.record_action.run(self.context, MockArg())
        self.assertEqual(mobile_ad_state["completed_cycles"], 1)
        self.assertTrue(mobile_ad_state["reward_recorded"])

        # Next ad starts
        self.ad_start_action.run(self.context, MockArg())
        self.assertFalse(mobile_ad_state["reward_recorded"])

        # Cycle 2 popup
        self.record_action.run(self.context, MockArg())
        self.assertEqual(mobile_ad_state["completed_cycles"], 2, "New popup must increment completed_cycles to 2")
        self.assertTrue(mobile_ad_state["reward_recorded"])

    def test_case5_max_cycles_3_hits_stop_and_blocks_continue(self):
        """Case 5: max_cycles=3，第三条奖励弹窗执行后命中 MobileAdCheckContinueCondition，走向红叉。"""
        self.reset_action.run(self.context, MockArg({"max_cycles": 3}))

        # Run 1 & 2
        for _ in range(2):
            self.record_action.run(self.context, MockArg())
            reco_res = self.check_reco.analyze(self.context, MockArg())
            self.assertIsNone(reco_res, "Reco must return None before reaching max_cycles")
            self.ad_start_action.run(self.context, MockArg())

        # Run 3
        self.record_action.run(self.context, MockArg())
        self.assertEqual(mobile_ad_state["completed_cycles"], 3)
        reco_res = self.check_reco.analyze(self.context, MockArg())
        self.assertIsNotNone(reco_res, "Reco must hit when completed_cycles >= max_cycles")
        self.assertEqual(reco_res, (0, 0, 10, 10))

    def test_case6_reco_retries_do_not_cause_side_effects(self):
        """Case 6: max_cycles=10，第一条奖励弹窗即使 candidate recognition 被 Maa 重试多次，completed_cycles 必须始终 == 1。"""
        self.reset_action.run(self.context, MockArg({"max_cycles": 10}))

        # First popup arrives
        self.record_action.run(self.context, MockArg())
        self.assertEqual(mobile_ad_state["completed_cycles"], 1)

        # Candidate recognition evaluated 20 times (simulating Maa polling)
        for _ in range(20):
            res = self.check_reco.analyze(self.context, MockArg())
            self.assertIsNone(res)

        self.assertEqual(mobile_ad_state["completed_cycles"], 1, "Recognition retries must never alter completed_cycles")

    def test_case7_log_tag_switches_per_task_and_resets_to_phone_default(self):
        self.reset_action.run(
            self.context,
            MockArg({"max_cycles": 3, "log_tag": "模拟器看广告"}),
        )
        self.assertEqual(mobile_ad_state["log_tag"], "模拟器看广告")

        self.reset_action.run(self.context, MockArg({"max_cycles": 3}))
        self.assertEqual(mobile_ad_state["log_tag"], "手机看广告")


if __name__ == "__main__":
    unittest.main()
