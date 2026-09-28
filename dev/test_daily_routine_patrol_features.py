"""日常收尾复用巡检魔力召唤、宝石融合的一次检查契约。"""

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


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class Context:
    def __init__(self, *enabled):
        self.enabled = enabled

    def get_node_data(self, name):
        return {"enabled": name in self.enabled}

    def override_pipeline(self, _values):
        pass


class DailyPatrolFeatureContract(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(daily_routine_state)
        self.routine = load("assets/resource/pipeline/routine/daily_routine.json")
        self.patrol = load("assets/resource/pipeline/features/patrol.json")
        self.extras = load("assets/resource/pipeline/features/patrol_extras.json")

    def tearDown(self):
        daily_routine_state.clear()
        daily_routine_state.update(self.saved)

    def init(self, context, param=None):
        arg = SimpleNamespace(custom_action_param=json.dumps(param) if param else "null")
        self.assertTrue(InitDailyRoutineAction().run(context, arg))

    def complete(self, name):
        param = self.routine[name]["custom_action_param"]
        arg = SimpleNamespace(custom_action_param=json.dumps(param))
        return DailyRoutineSubtaskDoneAction().run(Context(), arg)

    def test_ui_defaults_and_copies(self):
        paths = ("assets/interface.json", "client/interface.json", "client_avalonia/interface.json")
        raw = [(ROOT / path).read_bytes() for path in paths]
        self.assertEqual(raw[0], raw[1])
        self.assertEqual(raw[0], raw[2])
        ui = json.loads(raw[0])
        option = ui["option"]["日常收尾任务"]
        cases = {case["name"]: case for case in option["cases"]}
        for label, suffix in (("魔力召唤", "MagicSummon"), ("宝石融合", "GemFusion")):
            self.assertNotIn(label, option["default_case"])
            self.assertEqual(cases[label]["pipeline_override"], {
                "DailyRoutineEnable" + suffix: {"enabled": True}
            })
            self.assertFalse(self.routine["DailyRoutineEnable" + suffix]["enabled"])
        patrol_cases = ui["option"]["多鱼缸巡检子任务"]["cases"]
        self.assertEqual([case["name"] for case in patrol_cases], ["魔力召唤", "宝石融合"])

    def test_one_time_queue_and_explicit_hangup_opt_in(self):
        self.init(Context("DailyRoutineEnableMagicSummon", "DailyRoutineEnableGemFusion"))
        self.assertEqual(daily_routine_state["step"], "MAGIC_SUMMON")
        self.assertEqual(daily_routine_state["queue"], ["GEM_FUSION", "GREEN_WILD_CLAIM", "PRINCESS_CLAIM"])
        self.init(Context(), {"all_enabled": True})
        steps = [daily_routine_state["step"]] + daily_routine_state["queue"]
        self.assertNotIn("MAGIC_SUMMON", steps)
        self.assertNotIn("GEM_FUSION", steps)
        self.init(Context(), {"magic_summon": True, "gem_fusion": True})
        self.assertEqual(daily_routine_state["step"], "MAGIC_SUMMON")

    def test_reused_navigation_and_return_gate(self):
        dispatcher = self.routine["DailyRoutineDispatcher"]["next"]
        for suffix, step, entry in (
            ("MagicSummon", "MAGIC_SUMMON", "PatrolMagicOpenTreasure"),
            ("GemFusion", "GEM_FUSION", "PatrolGemFusionOpenTreasure"),
        ):
            start = "DailyRoutineStep" + suffix
            tank = "DailyRoutine" + suffix + "Tank"
            done = "DailyRoutine" + suffix + "Done"
            self.assertEqual(dispatcher.count(start), 1)
            self.assertEqual(self.routine[start]["custom_recognition_param"]["expected_step"], step)
            self.assertEqual(self.routine[tank]["template"], "主界面特征.png")
            self.assertEqual(self.routine[tank]["next"], [entry])
            self.assertIn(entry, self.extras)
            self.assertEqual(self.routine[done]["custom_action_param"], {
                "task_name": suffix, "expected_step": step
            })
            self.assertEqual(self.routine[done]["next"], ["DailyRoutineReturnIfActive", "DailyRoutineStandaloneDone"])
            self.assertEqual(self.extras["PatrolMagicConfirmPopup"]["template"], "绿色勾选按钮.png")
            for number in (1, 2, 3):
                verify = self.patrol[f"PatrolVerifyMainTank{number}AfterCycle"]
                self.assertEqual(verify["recognition"], "TemplateMatch")
                self.assertIn(done, verify["next"])
                self.assertLess(verify["next"].index(done), verify["next"].index("PatrolWaitLoop"))
        self.assertEqual(self.routine["DailyRoutineStepMagicSummon"]["next"][-3:],
                         ["PatrolMagicVerifyPage", "DailyRoutineMagicSummonTank", "PatrolMagicAbort"])
        self.assertEqual(self.routine["DailyRoutineStepGemFusion"]["next"][-4:],
                         ["PatrolGemFusionPutInStorage", "PatrolGemFusionVerifyPage",
                          "DailyRoutineGemFusionTank", "PatrolGemFusionAbort"])

    def test_completion_is_once_after_verified_tank(self):
        self.init(Context(), {"magic_summon": True, "gem_fusion": True})
        for suffix, next_step in (("MagicSummon", "GEM_FUSION"), ("GemFusion", "GREEN_WILD_CLAIM")):
            done = "DailyRoutine" + suffix + "Done"
            self.assertTrue(self.complete(done))
            self.assertEqual(daily_routine_state["tasks"][suffix]["status"], "DONE")
            self.assertEqual(daily_routine_state["step"], next_step)
            after = copy.deepcopy(daily_routine_state)
            self.assertTrue(self.complete(done))
            self.assertEqual(daily_routine_state, after)


if __name__ == "__main__":
    unittest.main()
