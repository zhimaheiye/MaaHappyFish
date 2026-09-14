#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Offline unit test for MobileAdContinueTestTask pipeline and templates."""

import json
import os
import unittest
from pathlib import Path
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestMobileAdContinuePipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline_file = REPO_ROOT / "assets" / "resource" / "pipeline" / "features" / "mobile_ads.json"
        self.tpl_check = REPO_ROOT / "assets" / "resource" / "image" / "mobile_ads" / "奖励弹窗_继续观看.png"
        self.tpl_capsule = REPO_ROOT / "assets" / "resource" / "image" / "mobile_ads" / "广告播放中_右上角胶囊.png"
        self.evidence_dir = REPO_ROOT / "dev" / "evidence" / "mobile_ads_investigation"

    def test_pipeline_nodes_and_structure(self):
        self.assertTrue(self.pipeline_file.exists(), "mobile_ads.json must exist")
        with open(self.pipeline_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("MobileAdTask", data)
        self.assertIn("MobileAdVerifyRewardPopup", data)
        self.assertIn("MobileAdClickContinueCheck", data)
        self.assertIn("MobileAdCheckContinueCondition", data)
        self.assertIn("MobileAdDone", data)

        popup_node = data["MobileAdVerifyRewardPopup"]
        self.assertEqual(popup_node["recognition"], "OCR")
        self.assertIn("恭喜你获得如下奖励", popup_node["expected"])
        self.assertEqual(popup_node["roi"], [600, 200, 400, 280])

        click_node = data["MobileAdClickContinueCheck"]
        self.assertEqual(click_node["recognition"], "TemplateMatch")
        self.assertEqual(click_node["template"], "mobile_ads/奖励弹窗_继续观看.png")
        self.assertEqual(click_node["action"], "Click")
        self.assertEqual(click_node["roi"], [930, 455, 120, 130])

    def test_templates_exist_and_readable(self):
        self.assertTrue(self.tpl_check.exists())
        self.assertTrue(self.tpl_capsule.exists())

        img_check = cv2.imdecode(np.fromfile(str(self.tpl_check), dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(img_check)
        self.assertEqual(img_check.shape[2], 3)

        img_cap = cv2.imdecode(np.fromfile(str(self.tpl_capsule), dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(img_cap)
        self.assertEqual(img_cap.shape[2], 3)

    def test_offline_template_matching_positive_and_negative(self):
        pos_frame_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "033.png"
        neg_frame_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "000.png"
        vid_frame_path = self.evidence_dir / "session_20260914_000244_ad2" / "maa" / "004.png"

        if not pos_frame_path.exists():
            self.skipTest("Ad2 evidence frame 033 not found")

        pos_img = cv2.imread(str(pos_frame_path))
        neg_img = cv2.imread(str(neg_frame_path))
        vid_img = cv2.imread(str(vid_frame_path))

        tpl_check = cv2.imdecode(np.fromfile(str(self.tpl_check), dtype=np.uint8), cv2.IMREAD_COLOR)
        tpl_cap = cv2.imdecode(np.fromfile(str(self.tpl_capsule), dtype=np.uint8), cv2.IMREAD_COLOR)

        # 1. Positive checkmark match
        roi_pos = pos_img[455:585, 930:1050]
        res_pos = cv2.matchTemplate(roi_pos, tpl_check, cv2.TM_CCOEFF_NORMED)
        _, max_pos, _, _ = cv2.minMaxLoc(res_pos)
        self.assertGreaterEqual(max_pos, 0.95, f"Checkmark score on positive frame: {max_pos}")

        # 2. Negative checkmark match (no popup)
        roi_neg = neg_img[455:585, 930:1050]
        res_neg = cv2.matchTemplate(roi_neg, tpl_check, cv2.TM_CCOEFF_NORMED)
        _, max_neg, _, _ = cv2.minMaxLoc(res_neg)
        self.assertLess(max_neg, 0.50, f"Checkmark score on negative frame: {max_neg}")

        # 3. Video capsule match on playing frame
        roi_vid = vid_img[10:90, 1350:1590]
        res_vid = cv2.matchTemplate(roi_vid, tpl_cap, cv2.TM_CCOEFF_NORMED)
        _, max_vid, _, _ = cv2.minMaxLoc(res_vid)
        self.assertGreaterEqual(max_vid, 0.65, f"Capsule score on video frame: {max_vid}")


if __name__ == "__main__":
    unittest.main()
