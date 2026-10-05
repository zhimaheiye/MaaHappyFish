"""2026-10-02 离线回归：牛奶回主页、浪漫满屋漏点、Agent 重启日程去重。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import local_state, my_action
from agent.fish_baby import SLOTS
from agent.runtime_state import hangup_schedule_state, daily_routine_state
from agent.my_reco import CheckHangupFriendGemDueReco, CheckHangupNoonDailyDueReco, FishBabyHomePageReco
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.resource import Resource
from maa.tasker import Tasker
from maa.library import Library

# 导入 Agent 装饰器会切换库模式；离线 Resource/CustomController 使用真实框架。
Library.open(Library.framework_libpath.parent, agent_server=False)


class SavedFrameController(CustomController):
    """仅回放磁盘图片，点击为空操作；不连接设备或物理窗口。"""
    def __init__(self, path):
        self.frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        super().__init__()

    def connect(self):
        return self.frame is not None

    def request_uuid(self):
        return "offline-desktop-incident"

    def get_features(self):
        return 0

    def screencap(self):
        return self.frame.copy()

    def click(self, x, y):
        return True


def nodes(name):
    return json.loads((ROOT / "assets/resource/pipeline/features" / name).read_text(encoding="utf-8"))


class RoundRecovery(unittest.TestCase):
    def test_native_milk_gate_and_failed_status_with_saved_frames(self):
        resource = Resource()
        self.assertTrue(resource.post_bundle(ROOT / "assets/resource").wait().succeeded)
        resource.register_custom_action("FailTaskAction", my_action.FailTaskAction())
        resource.register_custom_recognition("FishBabyHomePageReco", FishBabyHomePageReco())
        located = {n: {"timer_roi": slot["timer_roi"]} for n, slot in enumerate(SLOTS, 1)}

        class MilkGate(CustomAction):
            def run(self, context, argv):
                return my_action._fish_baby_wait_batch_result(context, "MILK_YELLOW", list(located), located)

        resource.register_custom_action("OfflineMilkGate", MilkGate())
        controller = SavedFrameController(ROOT / "dev/fixtures/fish_baby/home_sleeping_20261002.png")
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        self.assertTrue(tasker.post_task("OfflineGate", {"OfflineGate": {
            "recognition": "DirectHit", "action": "Custom", "custom_action": "OfflineMilkGate"
        }}).wait().succeeded)
        self.assertTrue(tasker.post_task("OfflineExitGate", {"OfflineExitGate": {
            **nodes("fish_baby.json")["FishBabyExitHome"], "action": "DoNothing", "next": []
        }}).wait().succeeded)
        self.assertTrue(tasker.post_task("FishBabyAbort").wait().failed)

    def test_native_retry_limit_on_unchanged_romantic_home(self):
        resource = Resource()
        self.assertTrue(resource.post_bundle(ROOT / "assets/resource").wait().succeeded)
        clicks = []

        class CountClick(my_action.ClickRecognizedCenterAction):
            def run(self, context, argv):
                clicks.append(tuple(argv.box))
                return super().run(context, argv)

        resource.register_custom_action("ClickRecognizedCenterAction", CountClick())
        resource.register_custom_action("FailTaskAction", my_action.FailTaskAction())
        controller = SavedFrameController(ROOT / "dev/fixtures/romantic_house/home_dropped_tap_20261002.png")
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        home = nodes("romantic_house.json")["RomanticHouseInHomePage"]
        result = tasker.post_task("RomanticHouseInHomePage", {"RomanticHouseInHomePage": {
            "post_delay": 0, "timeout": 100,
            "next": [n for n in home["next"] if not n.startswith("[JumpBack]")]
        }}).wait()
        self.assertTrue(result.failed)
        self.assertEqual(len(clicks), 3)

    def test_milk_postcondition_and_home_timer_positions(self):
        located = {1: {"timer_roi": (100, 200, 160, 45)}, 2: {"timer_roi": (300, 400, 160, 45)}}
        ctx = SimpleNamespace(tasker=SimpleNamespace(controller=object(), stopping=False, running=True))

        def run(kind, category=False, home=True, sleeping=(1, 2), cancelled=False):
            ctx.tasker.stopping = cancelled
            def ocr(context, frame, expected, roi):
                if expected == "请选择孵化方式":
                    return (1, 1, 1, 1) if category else None
                if expected == "开始孵化":
                    return (1, 1, 1, 1) if home else None
                for number in sleeping:
                    x, y, w, h = located[number]["timer_roi"]
                    if roi == (x, y + 30, w, h):
                        return (x, y + 30, w, h)
                return None
            with patch.object(my_action, "_capture_720p", return_value=object()), \
                 patch.object(my_action, "classify_sky", return_value="HOME"), \
                 patch.object(my_action, "_fish_baby_ocr_box", side_effect=ocr), \
                 patch.object(my_action.time, "monotonic", side_effect=[0, 0, 20]), \
                 patch.object(my_action.time, "sleep"):
                return my_action._fish_baby_wait_batch_result(ctx, kind, [1, 2], located)

        for kind in ("MILK_PINK", "MILK_YELLOW", "MILK_BLUEBERRY"):
            self.assertTrue(run(kind))
        self.assertTrue(run("FOOD_SUPER", category=True))
        self.assertFalse(run("FOOD_SUPER"))  # 鱼食后回主页不能借用牛奶收尾契约。
        self.assertFalse(run("MILK_YELLOW", home=False))
        self.assertFalse(run("MILK_YELLOW", sleeping=(1,)))
        self.assertFalse(run("MILK_YELLOW", cancelled=True))

    def test_stop_during_milk_is_not_reported_as_gate_error(self):
        import io
        from contextlib import redirect_stdout

        located = {1: {"baby": (10, 20), "timer_roi": (0, 0, 10, 10)}}
        ctx = SimpleNamespace(tasker=SimpleNamespace(controller=object(), stopping=True, running=False))

        def ocr(context, frame, expected, roi):
            if expected == "请选择孵化方式":
                assert roi == my_action.FISH_BABY_PROMPT_ROI
                return (930, 540, 20, 20)
            if expected in {"请选择牛奶", "请选择鱼宝宝", ".*牛奶.*"}:
                return (1, 1, 1, 1)
            return None

        stdout = io.StringIO()
        with patch.object(my_action, "_capture_720p", return_value=object()), \
             patch.object(my_action, "_fish_baby_ocr_box", side_effect=ocr), \
             patch.object(my_action, "_fish_baby_click"), \
             patch.object(my_action, "has_green_check", return_value=True), \
             patch.object(my_action.time, "sleep"), \
             redirect_stdout(stdout):
            result = my_action._fish_baby_run_batch(ctx, "MILK_YELLOW", [1], located)
        text = stdout.getvalue()
        self.assertFalse(result)
        self.assertIn("已收到停止请求", text)
        self.assertNotIn("ERROR", text)
        self.assertEqual(my_action.FISH_BABY_PROMPT_ROI, (930, 540, 330, 170))

    def test_round_accepts_sleeping_home_and_records_all_targets(self):
        located = {number: {"baby": (10, 20), "timer_roi": (number * 10, 200, 10, 20)}
                   for number in range(1, 9)}
        state = my_action.fish_baby_state
        ctx = SimpleNamespace(tasker=SimpleNamespace(controller=object(), stopping=False, running=True))
        with patch.dict(state, {"preferences": {n: "PET" for n in located},
                               "uniform_preferences": {"play": "PER_BABY", "food": "FOOD_SUPER", "milk": "MILK_YELLOW"}}, clear=False), \
             patch.object(my_action, "_capture_720p", return_value=object()), \
             patch.object(my_action, "_load_fish_baby_number_templates", return_value=object()), \
             patch.object(my_action, "locate_numbered_babies", return_value=located), \
             patch.object(my_action, "_fish_baby_ocr_box", side_effect=lambda c, f, e, r: (0, 0, 1, 1) if e == "请选择孵化方式" else None), \
             patch.object(my_action, "count_completed_hearts", return_value=4), \
             patch.object(my_action, "_fish_baby_run_batch", return_value=True) as batch, \
             patch.object(my_action, "_fish_baby_at_home", return_value=True), \
             patch.object(my_action, "_fish_baby_sleeping", return_value=set(located)) as asleep:
            self.assertTrue(my_action.FishBabyRunRoundAction().run(ctx, SimpleNamespace()))
            self.assertEqual(state["completed"], list(located))
            self.assertTrue(asleep.call_args.kwargs["at_home"])
            self.assertEqual([call.args[2] for call in batch.call_args_list if call.args[1] == "MILK_YELLOW"], [list(located)])

    def test_home_exit_gate_and_failure_are_not_false_success(self):
        fish = nodes("fish_baby.json")
        self.assertEqual(fish["FishBabyRunRound"]["next"], ["FishBabyExitIncubation", "FishBabyExitHome"])
        self.assertEqual(fish["FishBabyExitHome"]["all_of"], ["FishBabyAtHome", "FishBabyHomeStart"])
        self.assertEqual(fish["FishBabyExitHome"]["next"], ["FishBabyVerifyTankAfterRound"])
        for pipeline, name in ((fish, "FishBabyAbort"), (nodes("romantic_house.json"), "RomanticHouseAbort")):
            self.assertEqual(pipeline[name]["custom_action"], "FailTaskAction")
            self.assertNotIn("next", pipeline[name])
            self.assertNotIn("on_error", pipeline[name])
        self.assertFalse(my_action.FailTaskAction().run(None, SimpleNamespace(custom_action_param="null")))

    def test_romantic_dropped_tap_retries_only_on_verified_home(self):
        pipeline = nodes("romantic_house.json")
        self.assertEqual(pipeline["RomanticHouseStartRouter"]["custom_action"], "RomanticHouseResetEntryAction")
        cleared = []
        ctx = SimpleNamespace(clear_hit_count=lambda name: cleared.append(name) or True)
        for _ in range(2):
            self.assertTrue(my_action.RomanticHouseResetEntryAction().run(ctx, SimpleNamespace(custom_action_param="null")))
        self.assertEqual(cleared, ["RomanticHouseInHomePage"] * 2)
        home = pipeline["RomanticHouseInHomePage"]
        self.assertEqual(home["custom_action"], "ClickRecognizedCenterAction")
        self.assertEqual(home["on_error"], ["RomanticHouseAbort"])
        business = [n for n in home["next"] if not n.startswith("[JumpBack]")]
        self.assertEqual(business, ["RomanticHouseCheckDone", "RomanticHouseTryBless", "RomanticHouseNextCouple", "RomanticHouseInHomePage"])
        self.assertEqual(home["max_hit"], 3)
        # 页面级 next 契约：漏点留在主页才再点，舞台优先，无门禁则熔断。
        for pages, expected_clicks, success in ((["home", "stage"], 2, True), (["stage"], 1, True),
                                              (["home"] * 3, 3, False), (["unknown"], 1, False)):
            clicks = 0
            outcome = False
            for page in pages:
                clicks += 1
                candidate = next((n for n in business if (page == "stage" and n == "RomanticHouseCheckDone")
                                  or (page == "home" and n == "RomanticHouseInHomePage")), None)
                if candidate == "RomanticHouseCheckDone":
                    outcome = True
                    break
                if candidate is None or clicks >= home["max_hit"]:
                    break
            self.assertEqual((clicks, outcome), (expected_clicks, success))


class SchedulePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"MAAHAPPYFISH_STATE_DIR": self.tmp.name})
        self.env.start()
        self.state = patch.dict(hangup_schedule_state, {"resume_stack": [], **dict.fromkeys(local_state.HANGUP_SCHEDULE_KEYS)})
        self.state.start()
        self.daily = patch.dict(daily_routine_state, {"active": False})
        self.daily.start()

    def tearDown(self):
        self.daily.stop()
        self.state.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_actual_new_process_restores_attempts_without_stale_return_stack(self):
        local_state.save_local_state({"sea_otter": {"completed_runs": 2}})
        for key in local_state.HANGUP_SCHEDULE_KEYS:
            self.assertTrue(local_state.record_hangup_schedule_attempt(key, datetime(2026, 10, 2, 23)))
        code = 'import json; from agent.runtime_state import hangup_schedule_state; print(json.dumps(hangup_schedule_state))'
        restored = json.loads(subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, text=True))
        self.assertEqual(restored["resume_stack"], [])
        self.assertEqual(local_state.load_local_state()["sea_otter"], {"completed_runs": 2})
        hangup_schedule_state.update(restored)
        ctx = SimpleNamespace()
        arg = lambda now: SimpleNamespace(custom_recognition_param=json.dumps({"enabled": True, "now": now}))
        for now in ("2026-10-02T10:30:00", "2026-10-02T22:30:00"):
            self.assertIsNone(CheckHangupFriendGemDueReco().analyze(ctx, arg(now)))
        self.assertIsNone(CheckHangupNoonDailyDueReco().analyze(ctx, arg("2026-10-02T15:00:00")))
        self.assertIsNotNone(CheckHangupFriendGemDueReco().analyze(ctx, arg("2026-10-03T10:00:00")))
        self.assertIsNone(CheckHangupFriendGemDueReco().analyze(ctx, arg("2026-10-03T00:30:00")))

    def test_write_failure_stops_before_initializing_subtask_or_return_stack(self):
        arg = SimpleNamespace(custom_action_param='{"resume_to":"patrol"}')
        with patch.object(local_state, "save_local_state", return_value=False), \
             patch.object(my_action.InitDailyRoutineAction, "run") as daily, \
             patch.object(my_action.InitFriendGemStateAction, "run") as friend:
            self.assertFalse(my_action.InitHangupScheduledDailyAction().run(None, arg))
            self.assertFalse(my_action.InitHangupFriendGemAction().run(None, arg))
            daily.assert_not_called()
            friend.assert_not_called()
            self.assertEqual(hangup_schedule_state["resume_stack"], [])

    def test_invalid_dates_are_not_restored(self):
        local_state.save_local_state({"hangup_schedule": {"friend_gem_morning_date": "2026-99-99",
                                                          "noon_daily_last_date": [], "resume_stack": ["patrol"]}})
        self.assertEqual(local_state.get_hangup_schedule_dates(), {})
        self.assertFalse(local_state.record_hangup_schedule_attempt("resume_stack"))

    def test_initializers_persist_each_calendar_slot_before_start(self):
        arg = SimpleNamespace(custom_action_param='{"resume_to":"patrol"}')
        for hour, key, action in (
            (10, "friend_gem_morning_date", my_action.InitHangupFriendGemAction),
            (12, "noon_daily_last_date", my_action.InitHangupScheduledDailyAction),
            (22, "friend_gem_evening_date", my_action.InitHangupFriendGemAction),
        ):
            def started(context, argv):
                self.assertEqual(local_state.get_hangup_schedule_dates()[key], "2026-10-02")
                return True
            with patch.object(my_action, "datetime") as clock, \
                 patch.object(my_action.InitDailyRoutineAction, "run", side_effect=started), \
                 patch.object(my_action.InitFriendGemStateAction, "run", side_effect=started):
                clock.now.return_value = datetime(2026, 10, 2, hour)
                self.assertTrue(action().run(None, arg))
                self.assertEqual(hangup_schedule_state[key], "2026-10-02")


if __name__ == "__main__":
    unittest.main()
