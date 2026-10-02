"""购买鱼食/鱼宝接入日常的离线配置、调度与完成契约。"""

import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.my_action import InitDailyRoutineAction, DailyRoutineSubtaskDoneAction
from agent.runtime_state import daily_routine_state


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class Context:
    def __init__(self, *enabled):
        self.enabled = enabled
        self.overrides = {}

    def get_node_data(self, name):
        return {"enabled": name in self.enabled}

    def override_pipeline(self, values):
        self.overrides.update(values)


class DailyFoodBabyContract(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(daily_routine_state)
        self.ui = load("assets/interface.json")
        self.routine = load("assets/resource/pipeline/routine/daily_routine.json")
        self.food = load("assets/resource/pipeline/features/buy_fish_food.json")
        self.baby = load("assets/resource/pipeline/features/fish_baby.json")

    def tearDown(self):
        daily_routine_state.clear()
        daily_routine_state.update(self.saved)

    def init(self, context, param=None):
        argv = SimpleNamespace(custom_action_param=json.dumps(param) if param else "null")
        self.assertTrue(InitDailyRoutineAction().run(context, argv))

    def complete(self, param):
        return DailyRoutineSubtaskDoneAction().run(
            Context(), SimpleNamespace(custom_action_param=json.dumps(param)))

    def test_ui_reuses_standalone_inputs(self):
        tasks = {task["name"]: task for task in self.ui["task"]}
        options = self.ui["option"]
        cases = {case["name"]: case for case in options["日常收尾任务"]["cases"]}
        for name in ("购买鱼食", "鱼宝乐园"):
            self.assertEqual(cases[name]["option"], tasks[name]["option"])
            self.assertNotIn(name, options["日常收尾任务"]["default_case"])
        quantity = options[cases["购买鱼食"]["option"][0]]
        self.assertEqual(quantity["inputs"][0]["name"], "袋数")
        self.assertEqual(quantity["inputs"][0]["pipeline_type"], "int")
        for node in ("BuyFishFoodStartAtDetail", "BuyFishFoodPurchaseOnDetail"):
            self.assertEqual(quantity["pipeline_override"][node]["custom_action_param"]["bags"], "{袋数}")
        self.assertEqual(set(cases["购买鱼食"]["pipeline_override"]), {"DailyRoutineEnableBuyFishFood"})

    def test_ui_switches_reach_queue_and_completion(self):
        ctx = Context("DailyRoutineEnableBuyFishFood", "DailyRoutineEnableFishBaby")
        self.init(ctx)
        self.assertEqual(daily_routine_state["step"], "BUY_FISH_FOOD")
        self.assertEqual(daily_routine_state["queue"], ["FISH_BABY"])
        for task, step in (("BuyFishFood", "BUY_FISH_FOOD"), ("FishBaby", "FISH_BABY")):
            param = {"task_name": task, "expected_step": step}
            self.assertTrue(self.complete(param))
            self.assertEqual(daily_routine_state["tasks"][task]["status"], "DONE")
            after = copy.deepcopy(daily_routine_state)
            self.assertTrue(self.complete(param))
            self.assertEqual(daily_routine_state, after)
        self.assertEqual(daily_routine_state["step"], "ALL_DONE")
        message = ctx.overrides["DailyRoutineInitLog"]["focus"]["Node.Action.Succeeded"]
        self.assertIn("已选择：购买鱼食、鱼宝乐园", message)

    def test_parameters_and_hangup_defaults(self):
        for key, step in (("buy_fish_food", "BUY_FISH_FOOD"), ("fish_baby", "FISH_BABY")):
            self.init(Context(), {key: True})
            self.assertEqual(daily_routine_state["step"], step)
        self.init(Context(), {"all_enabled": True})
        steps = [daily_routine_state["step"]] + daily_routine_state["queue"]
        self.assertNotIn("BUY_FISH_FOOD", steps)
        self.assertNotIn("FISH_BABY", steps)
        self.init(Context(), {"all_enabled": True, "buy_fish_food": True, "fish_baby": True})
        steps = [daily_routine_state["step"]] + daily_routine_state["queue"]
        self.assertLess(steps.index("BUY_FISH_FOOD"), steps.index("FISH_BABY"))
        self.assertLess(steps.index("FISH_BABY"), steps.index("BAND_FISH_PASS2"))

    def test_standalone_and_invalid_completion_do_not_advance(self):
        self.init(Context(), {"buy_fish_food": True})
        before = copy.deepcopy(daily_routine_state)
        self.assertFalse(self.complete(None))
        self.assertFalse(self.complete({"task_name": "FishBaby", "expected_step": "BUY_FISH_FOOD"}))
        self.assertEqual(daily_routine_state, before)
        daily_routine_state["active"] = False
        before = copy.deepcopy(daily_routine_state)
        self.assertTrue(self.complete({"task_name": "BuyFishFood", "expected_step": "BUY_FISH_FOOD"}))
        self.assertEqual(daily_routine_state, before)

    def test_completion_requires_tank_and_has_dual_exit(self):
        for pipeline, name, step, task in (
            (self.food, "BuyFishFoodDone", "BUY_FISH_FOOD", "BuyFishFood"),
            (self.baby, "FishBabyVerifyTankAfterRound", "FISH_BABY", "FishBaby"),
            (self.baby, "FishBabySkipAllVerifyTank", "FISH_BABY", "FishBaby"),
        ):
            node = pipeline[name]
            self.assertEqual(node["recognition"], "TemplateMatch")
            self.assertEqual(node["template"], "主界面特征.png")
            self.assertEqual(node["custom_action"], "DailyRoutineSubtaskDoneAction")
            self.assertEqual(node["custom_action_param"]["expected_step"], step)
            self.assertEqual(node["custom_action_param"]["task_name"], task)
            self.assertEqual(node["next"][-2:], ["DailyRoutineReturnIfActive", "DailyRoutineStandaloneDone"])
            failure = pipeline[node["on_error"][0]]
            if task == "FishBaby":
                self.assertEqual(failure["custom_action"], "FailTaskAction")
                self.assertNotIn("next", failure)
                self.assertNotIn("on_error", failure)
            else:
                self.assertEqual(failure["action"], "StopTask")
        for node in ("BuyFishFoodStartAtDetail", "BuyFishFoodPurchaseOnDetail"):
            self.assertEqual(self.food[node]["next"][-1], "BuyFishFoodDone")
        self.assertEqual(self.baby["FishBabySkipAll"]["next"], ["FishBabySkipAllDaily", "DailyRoutineStandaloneDone"])
        self.assertEqual(self.baby["FishBabySkipAllDaily"]["custom_recognition"], "CheckDailyRoutineActiveReco")
        self.init(Context(), {"fish_baby": True})
        self.assertTrue(self.complete(self.baby["FishBabySkipAllVerifyTank"]["custom_action_param"]))
        self.assertEqual(daily_routine_state["tasks"]["FishBaby"]["status"], "SKIPPED")
        self.assertEqual(daily_routine_state["step"], "ALL_DONE")

    def test_dispatch_and_existing_navigation(self):
        dispatcher = self.routine["DailyRoutineDispatcher"]["next"]
        for suffix, step, entry in (("BuyFishFood", "BUY_FISH_FOOD", "BuyFishFoodTask"), ("FishBaby", "FISH_BABY", "FishBabyTask")):
            name = "DailyRoutineStep" + suffix
            self.assertEqual(dispatcher.count(name), 1)
            self.assertEqual(self.routine[name]["custom_recognition_param"]["expected_step"], step)
            self.assertEqual(self.routine[name]["next"][-1], entry)
            self.assertFalse(self.routine["DailyRoutineEnable" + suffix]["enabled"])
        router = self.baby["FishBabyStartRouter"]["next"]
        for name in ("FishBabyIncubationCategory", "FishBabyIncubationFoodItems", "FishBabyIncubationPlayItems", "FishBabyIncubationMilkItems", "FishBabyAtHome", "FishBabyAtMainTank"):
            self.assertIn(name, router)
        self.assertLess(router.index("FishBabyIncubationCategory"), router.index("FishBabyAtMainTank"))


if __name__ == "__main__":
    unittest.main()
