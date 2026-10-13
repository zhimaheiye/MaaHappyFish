"""Cold-start transition must outlive the observed 20-second splash screen."""

import json
import unittest
from pathlib import Path


COMMON = Path(__file__).resolve().parents[1] / "assets/resource/pipeline/common/common.json"


class StartAppColdBootContract(unittest.TestCase):
    def test_start_chain_waits_for_a_verified_main_screen(self):
        nodes = json.loads(COMMON.read_text(encoding="utf-8"))
        self.assertGreaterEqual(nodes["StartAppTask"]["timeout"], 90000)
        self.assertGreaterEqual(nodes["ClickEnterGame"]["timeout"], 90000)
        self.assertIn("ConfirmMainScreen", nodes["StartAppTask"]["next"])
        self.assertIn("ConfirmMainScreen", nodes["ClickEnterGame"]["next"])
        self.assertEqual(nodes["ConfirmMainScreen"]["recognition"], "TemplateMatch")
        self.assertEqual(nodes["ConfirmMainScreen"]["action"], "DoNothing")


if __name__ == "__main__":
    unittest.main()
