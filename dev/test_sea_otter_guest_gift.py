"""海獭拜访礼物弹窗和两份真实错误图的离线安全回归。"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.my_action import SeaOtterCloseGuestGiftAction, SeaOtterUnknownScreenWaitAction
from agent.runtime_state import sea_otter_gem_state


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = json.loads((ROOT / "assets/resource/pipeline/features/sea_otter_gem.json").read_text(encoding="utf-8"))
PATROL = json.loads((ROOT / "assets/resource/pipeline/features/patrol.json").read_text(encoding="utf-8"))


class _Controller:
    def __init__(self):
        self.clicks = []
        self.succeeded = True

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return self

    def wait(self):
        return self


class _Context:
    def __init__(self, controller, button=(904, 610, 65, 35)):
        self.tasker = SimpleNamespace(controller=controller, running=True, stopping=False)
        self.button = button

    def run_recognition(self, name, frame):
        if frame != "gift":
            return SimpleNamespace(hit=False)
        box = self.button if name == "SeaOtterGuestGiftConfirm" else (317, 450, 764, 39)
        return SimpleNamespace(hit=True, box=box)


class SeaOtterGuestGiftTests(unittest.TestCase):
    def test_popup_precedes_underlying_stamina_in_all_friend_routers(self):
        for name, later in (
            ("SeaOtterStartRouter", "SeaOtterStartAtFriendTank"),
            ("SeaOtterFriendRouter", "SeaOtterHasStaminaPanel"),
            ("SeaOtterKnownFriendRouter", "SeaOtterHarvestable"),
        ):
            with self.subTest(router=name):
                choices = PIPELINE[name]["next"]
                self.assertLess(choices.index("SeaOtterGuestGiftPopup"), choices.index(later))
        popup = PIPELINE["SeaOtterGuestGiftPopup"]
        self.assertEqual(popup["all_of"], ["SeaOtterGuestGiftText", "SeaOtterGuestGiftConfirm"])
        self.assertEqual(popup["on_error"], ["SeaOtterNavigationFailed"])

    def test_clicks_only_recognized_button_then_confirms_two_clear_frames(self):
        controller = _Controller()
        context = _Context(controller)
        frames = iter(["gift", "clear", "clear"])
        with patch("agent.my_action._capture_720p", side_effect=lambda _: next(frames)), patch("agent.my_action.time.sleep"):
            result = SeaOtterCloseGuestGiftAction().run(context, SimpleNamespace(custom_action_param=None))
        self.assertTrue(result)
        self.assertEqual(controller.clicks, [(936, 627)])

    def test_refuses_off_target_button(self):
        controller = _Controller()
        context = _Context(controller, button=(300, 610, 65, 35))
        with patch("agent.my_action._capture_720p", return_value="gift"):
            result = SeaOtterCloseGuestGiftAction().run(context, SimpleNamespace(custom_action_param=None))
        self.assertFalse(result)
        self.assertEqual(controller.clicks, [])

    def test_never_reports_closed_without_positive_popup_frame(self):
        controller = _Controller()
        context = _Context(controller)
        with patch("agent.my_action._capture_720p", return_value="clear"), patch("agent.my_action.time.sleep"):
            result = SeaOtterCloseGuestGiftAction().run(context, SimpleNamespace(custom_action_param=None))
        self.assertFalse(result)
        self.assertEqual(controller.clicks, [])

    def test_gem_exchange_accepts_live_recipe_count_without_loosening_tab_gate(self):
        self.assertEqual(PIPELINE["SeaOtterHomeAtGemExchange"]["all_of"],
                         ["SeaOtterGemExchangeTab", "SeaOtterGemExchangeRecipes"])
        self.assertIn("宝石兑换鱼配方数", PIPELINE["SeaOtterGemExchangeRecipes"]["expected"])

    def test_unknown_friend_screen_cannot_wait_forever(self):
        node = PIPELINE["SeaOtterWaitScreen"]
        self.assertEqual(node["custom_action"], "SeaOtterUnknownScreenWaitAction")
        self.assertEqual(node["on_error"], ["SeaOtterNavigationFailed"])
        context = _Context(_Controller())
        action = SeaOtterUnknownScreenWaitAction()
        with patch.dict(sea_otter_gem_state, {"unknown_screen_waits": 0}):
            for _ in range(11):
                self.assertTrue(action.run(context, SimpleNamespace(custom_action_param=None)))
            self.assertFalse(action.run(context, SimpleNamespace(custom_action_param=None)))

    def test_picker_thresholds_cover_two_live_scores(self):
        self.assertLessEqual(PATROL["PatrolSelectTank1FromPicker"]["threshold"], 0.7545)
        self.assertLessEqual(PATROL["PatrolSelectTank2FromPicker"]["threshold"], 0.7396)
        self.assertIn("PatrolVerifyTank1Main", PATROL["PatrolSelectTank1FromPicker"]["next"])
        self.assertIn("PatrolVerifyTank2Main", PATROL["PatrolSelectTank2FromPicker"]["next"])


if __name__ == "__main__":
    unittest.main()
