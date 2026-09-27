"""乐队鱼结算必须有页面身份；绿色鱼/按钮、其它确定按钮均不得误路由。"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from maa.define import Rect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.my_action import _band_fish_settlement_button
from agent.my_reco import CheckBandFishSettlementReco


class Context:
    def __init__(self, title=False, confirm=False):
        self.title = title
        self.confirm = confirm
        self.calls = []

    def run_recognition(self, name, image):
        self.calls.append(name)
        if name == "BandFishStartAtSettlement":
            box = CheckBandFishSettlementReco().analyze(self, SimpleNamespace(image=image))
            return SimpleNamespace(hit=box is not None, box=box)
        hit = self.title if name == "BandFishSettlementTitle" else self.confirm
        return SimpleNamespace(hit=hit, box=Rect(595, 662, 90, 30))


class SettlementContract(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.frame[650:700, 595:685] = (0, 255, 0)

    def test_green_pixels_are_not_settlement(self):
        context = Context(confirm=True)
        self.assertIsNone(_band_fish_settlement_button(context, self.frame))
        self.assertNotIn("BandFishSettlementConfirm", context.calls)

    def test_title_without_button_is_not_clickable(self):
        self.assertIsNone(_band_fish_settlement_button(Context(title=True), self.frame))

    def test_confirm_center_requires_both_positive_gates(self):
        self.assertEqual(_band_fish_settlement_button(Context(True, True), self.frame), (640, 677))
        self.assertIsNone(_band_fish_settlement_button(Context(True, True), None))

    def test_known_page_rois_and_deepest_first(self):
        pipeline = json.loads((ROOT / "assets/resource/pipeline/features/band_fish.json").read_text(encoding="utf-8"))
        self.assertEqual(pipeline["BandFishStartRouter"]["next"][5], "BandFishStartAtSettlement")
        for node, expected, roi in (
            ("BandFishSettlementTitle", "^我的乐章$", [500, 170, 280, 100]),
            ("BandFishSettlementConfirm", "^确定$", [500, 630, 280, 85]),
        ):
            self.assertEqual(pipeline[node]["expected"], expected)
            self.assertEqual(pipeline[node]["roi"], roi)
            self.assertEqual(pipeline[node]["action"], "DoNothing")


if __name__ == "__main__":
    unittest.main()
