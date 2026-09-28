"""日常收尾第一张活动卡片的安全路由与可选领取。"""

import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.my_action import DailyActivityEnergyClaimAction, DailyRoutineSubtaskDoneAction, InitDailyRoutineAction
from agent.runtime_state import daily_routine_state


class Controller:
    def __init__(self):
        self.clicks = []

    def post_screencap(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        return SimpleNamespace(wait=lambda: None, get=lambda: frame)

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=True))


class Context:
    def __init__(self, enabled=(), page=True, claim_hits=()):
        self.enabled = enabled
        self.page = page
        self.claim_hits = iter(claim_hits)
        self.tasker = SimpleNamespace(controller=Controller(), stopping=False, running=True)

    def get_node_data(self, name):
        return {"enabled": name in self.enabled}

    def override_pipeline(self, _values):
        pass

    def run_recognition(self, name, _frame):
        if name == "DailyActivityEnergyPage":
            return SimpleNamespace(hit=self.page, box=(1219, 22, 37, 49))
        if name == "DailyActivityEnergyClaimButton":
            return SimpleNamespace(hit=next(self.claim_hits, False), box=(600, 350, 80, 40))
        if name == "DailyActivityEnergyListBack":
            return SimpleNamespace(hit=False, box=(0, 0, 0, 0))
        raise AssertionError(name)


class DailyActivityEnergyTest(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(daily_routine_state)
        self.pipeline = json.loads((ROOT / "assets/resource/pipeline/routine/daily_routine.json").read_text(encoding="utf-8"))

    def tearDown(self):
        daily_routine_state.clear()
        daily_routine_state.update(self.saved)

    def test_default_off_and_one_queue_slot(self):
        files = [ROOT / p for p in ("assets/interface.json", "client/interface.json", "client_avalonia/interface.json")]
        self.assertEqual(files[0].read_bytes(), files[1].read_bytes())
        self.assertEqual(files[0].read_bytes(), files[2].read_bytes())
        option = json.loads(files[0].read_text(encoding="utf-8"))["option"]["日常收尾任务"]
        label = "领取活动体力（酿月食香）"
        self.assertNotIn(label, option["default_case"])
        case = next(c for c in option["cases"] if c["name"] == label)
        self.assertEqual(case["pipeline_override"], {"DailyRoutineEnableActivityEnergy": {"enabled": True}})
        self.assertFalse(self.pipeline["DailyRoutineEnableActivityEnergy"]["enabled"])
        action = InitDailyRoutineAction()
        self.assertTrue(action.run(Context(), SimpleNamespace(custom_action_param='{"all_enabled":true}')))
        self.assertNotIn("ACTIVITY_ENERGY", [daily_routine_state["step"], *daily_routine_state["queue"]])
        self.assertTrue(action.run(Context(("DailyRoutineEnableActivityEnergy",)), SimpleNamespace(custom_action_param="null")))
        self.assertEqual(daily_routine_state["step"], "ACTIVITY_ENERGY")
        self.assertEqual(daily_routine_state["queue"].count("ACTIVITY_ENERGY"), 0)

    def test_page_gates_and_first_card_only(self):
        p = self.pipeline
        self.assertNotIn("[JumpBack]GlobalActivityPagePopup", p["DailyRoutineTask"]["next"])
        self.assertLess(p["DailyRoutineDispatcher"]["next"].index("DailyRoutineStepActivityEnergy"),
                        p["DailyRoutineDispatcher"]["next"].index("[JumpBack]GlobalActivityPagePopup"))
        self.assertEqual([name for name in p["DailyRoutineStepActivityEnergy"]["next"]
                          if not name.startswith("[JumpBack]")],
                         ["DailyActivityEnergyPage", "DailyActivityEnergyListPage", "DailyActivityEnergyAtTank"])
        self.assertEqual(p["DailyActivityEnergyEntry"]["template"], "精彩活动_入口.png")
        self.assertEqual(p["DailyActivityEnergyEntry"]["roi"], [27, 187, 58, 39])
        self.assertEqual(p["DailyActivityEnergyListPage"]["template"], "活动页面_退出.png")
        self.assertEqual(p["DailyActivityEnergyCard1"]["expected"], "酿月食香")
        x, y, w, h = p["DailyActivityEnergyCard1"]["target"]
        self.assertTrue(36 <= x and x + w <= 36 + 221 and 208 <= y and y + h <= 208 + 410)
        self.assertEqual(p["DailyActivityEnergyPage"]["template"], "酿月食香_关闭.png")
        self.assertEqual(p["DailyActivityEnergyClaimButton"]["expected"], "^收下$")
        self.assertEqual(p["DailyActivityEnergyClose"]["roi"], [1219, 22, 37, 49])
        self.assertEqual(p["DailyActivityEnergyListBack"]["template"], "活动页面_退出.png")
        self.assertEqual(p["DailyActivityEnergyVerifyTank"]["template"], "主界面特征.png")
        self.assertEqual(p["DailyActivityEnergyVerifyTank"]["custom_action_param"],
                         {"task_name": "ActivityEnergy", "expected_step": "ACTIVITY_ENERGY"})
        for name in ("精彩活动_入口.png", "酿月食香_关闭.png", "活动页面_退出.png"):
            self.assertTrue((ROOT / "assets/resource/image" / name).is_file())

    @patch("agent.my_action.time.sleep", return_value=None)
    def test_claim_only_when_seen_and_stop_if_page_unknown(self, _sleep):
        action = DailyActivityEnergyClaimAction()
        arg = SimpleNamespace(custom_action_param="null")
        missing = Context(page=False)
        self.assertFalse(action.run(missing, arg))
        self.assertEqual(missing.tasker.controller.clicks, [])
        no_claim = Context(claim_hits=[False] * 4)
        self.assertTrue(action.run(no_claim, arg))
        self.assertEqual(no_claim.tasker.controller.clicks, [])
        claim = Context(claim_hits=[True, False, False])
        self.assertTrue(action.run(claim, arg))
        self.assertEqual(claim.tasker.controller.clicks, [(640, 370)])
        stuck = Context(claim_hits=[True] * 9)
        self.assertFalse(action.run(stuck, arg))
        self.assertEqual(stuck.tasker.controller.clicks, [(640, 370)])

    def test_complete_only_after_verified_tank(self):
        context = Context()
        self.assertTrue(InitDailyRoutineAction().run(context, SimpleNamespace(custom_action_param='{"activity_energy":true}')))
        arg = SimpleNamespace(custom_action_param=json.dumps(
            self.pipeline["DailyActivityEnergyVerifyTank"]["custom_action_param"]
        ))
        self.assertTrue(DailyRoutineSubtaskDoneAction().run(context, arg))
        self.assertEqual(daily_routine_state["tasks"]["ActivityEnergy"]["status"], "DONE")
        step = daily_routine_state["step"]
        self.assertTrue(DailyRoutineSubtaskDoneAction().run(context, arg))
        self.assertEqual(daily_routine_state["step"], step)


if __name__ == "__main__":
    unittest.main()
