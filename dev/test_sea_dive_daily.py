"""深海寻鱼免费流程的独立入口、日常收尾接入与安全边界。"""

import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.my_action import DailyRoutineSubtaskDoneAction, InitDailyRoutineAction
from agent.runtime_state import daily_routine_state


class Context:
    def __init__(self, enabled=()):
        self.enabled = set(enabled)
        self.overrides = []

    def get_node_data(self, name):
        return {"enabled": name in self.enabled}

    def override_pipeline(self, value):
        self.overrides.append(value)


class SeaDiveDailyTest(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(daily_routine_state)
        self.routine = json.loads((ROOT / "assets/resource/pipeline/routine/daily_routine.json").read_text(encoding="utf-8"))
        self.dive = json.loads((ROOT / "assets/resource/pipeline/features/sea_dive.json").read_text(encoding="utf-8"))

    def tearDown(self):
        daily_routine_state.clear()
        daily_routine_state.update(self.saved)

    def test_interface_label_and_opt_in(self):
        paths = [ROOT / path for path in ("assets/interface.json", "client/interface.json", "client_avalonia/interface.json")]
        self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())
        self.assertEqual(paths[0].read_bytes(), paths[2].read_bytes())
        interface = json.loads(paths[0].read_text(encoding="utf-8"))
        independent = next(task for task in interface["task"] if task["entry"] == "SeaDiveTask")
        self.assertFalse(independent["default_check"])
        for text in ("2 次免费", "立即返航", "不移动潜艇", "不继续下潜", "x12"):
            self.assertIn(text, independent["description"])
        option = interface["option"]["日常收尾任务"]
        case = next(case for case in option["cases"] if case["name"].startswith("深海寻鱼"))
        self.assertNotIn(case["name"], option["default_case"])
        self.assertEqual(case["pipeline_override"], {"DailyRoutineEnableSeaDive": {"enabled": True}})
        self.assertFalse(self.routine["DailyRoutineEnableSeaDive"]["enabled"])

    def test_scheduled_default_off_explicit_opt_in_and_order(self):
        action = InitDailyRoutineAction()
        self.assertTrue(action.run(Context(), SimpleNamespace(custom_action_param='{"all_enabled":true}')))
        self.assertNotIn("SEA_DIVE", [daily_routine_state["step"], *daily_routine_state["queue"]])
        self.assertTrue(action.run(Context(), SimpleNamespace(custom_action_param='{"sea_dive":true}')))
        self.assertEqual(daily_routine_state["step"], "SEA_DIVE")
        self.assertEqual(daily_routine_state["queue"], [])
        self.assertTrue(action.run(Context(("DailyRoutineEnableSeaDive",)), SimpleNamespace(custom_action_param="null")))
        self.assertEqual(daily_routine_state["step"], "SEA_DIVE")
        self.assertIn("DailyRoutineStepSeaDive", self.routine["DailyRoutineDispatcher"]["next"])
        self.assertEqual(self.routine["DailyRoutineStepSeaDive"]["next"][-1], "SeaDiveTask")
        self.assertLess(self.routine["DailyRoutineDispatcher"]["next"].index("DailyRoutineStepFishing"),
                        self.routine["DailyRoutineDispatcher"]["next"].index("DailyRoutineStepSeaDive"))
        self.assertLess(self.routine["DailyRoutineDispatcher"]["next"].index("DailyRoutineStepSeaDive"),
                        self.routine["DailyRoutineDispatcher"]["next"].index("DailyRoutineStepGemGiftBox"))

    def test_only_verified_main_tank_advances_routine(self):
        self.assertEqual(self.dive["SeaDiveVerifyMainTank1"]["next"][-2:],
                         ["DailyRoutineSeaDiveDone", "DailyRoutineStandaloneDone"])
        done = self.routine["DailyRoutineSeaDiveDone"]
        self.assertEqual(done["custom_recognition_param"], {"expected_step": "SEA_DIVE"})
        self.assertEqual(done["custom_action_param"], {"task_name": "SeaDive", "expected_step": "SEA_DIVE"})
        self.assertTrue(InitDailyRoutineAction().run(Context(), SimpleNamespace(custom_action_param='{"sea_dive":true}')))
        arg = SimpleNamespace(custom_action_param=json.dumps(done["custom_action_param"]))
        self.assertTrue(DailyRoutineSubtaskDoneAction().run(Context(), arg))
        self.assertEqual(daily_routine_state["tasks"]["SeaDive"]["status"], "DONE")
        self.assertEqual(daily_routine_state["step"], "ALL_DONE")
        self.assertTrue(DailyRoutineSubtaskDoneAction().run(Context(), arg))
        self.assertEqual(daily_routine_state["step"], "ALL_DONE")

    def test_paid_and_unknown_never_click_dive(self):
        self.assertEqual(self.dive["SeaDiveFreeStateRouter"]["next"],
                         ["SeaDivePaidState", "SeaDiveFreeAvailable"])
        self.assertEqual(self.dive["SeaDiveFreeStateRouter"]["on_error"],
                         ["SeaDiveUnknownState"])
        self.assertGreaterEqual(self.dive["SeaDiveVerifyHomeAfterCycle"].get("post_delay", 0), 5000)
        self.assertEqual(self.dive["SeaDivePaidState"]["action"], "DoNothing")
        self.assertEqual(self.dive["SeaDivePaidState"]["next"], ["SeaDiveHomeClose"])
        self.assertEqual(self.dive["SeaDiveFreeAvailable"]["recognition"], "TemplateMatch")
        self.assertEqual(self.dive["SeaDiveChoose100m"]["expected"], "100米")
        self.assertEqual(self.dive["SeaDiveInGame"]["next"], ["SeaDiveClickInGameReturn"])
        self.assertEqual(self.dive["SeaDiveResultPage"]["next"], ["SeaDiveClickResultReturn"])
        for name in ("SeaDiveUnknownState", "SeaDiveAbortUnknownPage"):
            self.assertEqual(self.dive[name]["custom_action"], "FailTaskAction")


if __name__ == "__main__":
    unittest.main()
