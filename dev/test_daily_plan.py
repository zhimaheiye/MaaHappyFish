"""Saved MFA daily configuration reuse, isolated execution and lifecycle regression."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.daily_plan import read_daily_plan, compile_daily_options, daily_task_name
from agent.my_action import InitHangupScheduledDailyAction, InitDailyRoutineAction, DailyRoutineFinishAction
from agent.my_reco import CheckHangupNoonDailyDueReco, CheckHangupFriendGemDueReco
from agent.runtime_state import daily_routine_state, hangup_schedule_state
from agent.task_lifecycle import DailyTaskLifecycleSink
from agent import local_state
from maa.event_sink import NotificationType

INTERFACE = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
BASE = {}
for path in (ROOT / "assets/resource/pipeline").rglob("*.json"):
    BASE.update(json.loads(path.read_text(encoding="utf-8")))


def arg(param=None):
    return SimpleNamespace(custom_action_param=json.dumps(param or {}), custom_recognition_param=json.dumps(param or {}))


def saved_daily(name="午间方案", selected=None):
    return {"name": "日常收尾", "display_name_override": name, "entry": "DailyRoutineTask", "default_check": False,
            "option": [{"name": "日常收尾任务", "selected_cases": selected or [], "sub_options": []}]}


class Context:
    def __init__(self, nodes=None):
        self.nodes = copy.deepcopy(nodes or BASE)
        self.tasker = SimpleNamespace(resource=SimpleNamespace(get_node_data=lambda name: copy.deepcopy(BASE.get(name))))
        self.runs = []
        self.fail_child = False
        self.stop_child = False

    def get_node_data(self, name):
        return self.nodes.get(name)

    def override_pipeline(self, overrides):
        for name, override in overrides.items():
            self.nodes.setdefault(name, {}).update(copy.deepcopy(override))
        return True

    def clone(self):
        child = Context(self.nodes)
        child.runs = self.runs
        child.fail_child = self.fail_child
        child.stop_child = self.stop_child
        return child

    def run_task(self, entry):
        self.runs.append((entry, copy.deepcopy(self.nodes)))
        assert entry == "HangupPrepareDaily"
        assert local_state.get_hangup_schedule_dates().get("noon_daily_last_date")
        if self.fail_child:
            daily_routine_state.update(active=True, step="FISH_BABY")
            return SimpleNamespace(status=SimpleNamespace(succeeded=False))
        if self.stop_child:
            return SimpleNamespace(status=SimpleNamespace(succeeded=True))
        assert InitDailyRoutineAction().run(self, arg(self.nodes["DailyRoutineTask"]["custom_action_param"]))
        daily_routine_state.update(step="ALL_DONE", queue=[])
        assert DailyRoutineFinishAction().run(self, arg())
        return SimpleNamespace(status=SimpleNamespace(succeeded=True))


class DailyPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config/instances").mkdir(parents=True)
        (self.root / "interface.json").write_text(json.dumps(INTERFACE), encoding="utf-8")
        self.write_tasks([saved_daily()])
        self.env = patch.dict(os.environ, {"MFA_INSTANCE_ID": "test-instance", "MAAHAPPYFISH_STATE_DIR": str(self.root / "state")})
        self.env.start()
        self.cwd = Path.cwd()
        os.chdir(self.root)
        daily_routine_state.update(active=False, step="INIT", queue=[], outcome=None)
        hangup_schedule_state.update(resume_stack=[], noon_daily_last_date=None, friend_gem_morning_date=None, friend_gem_evening_date=None)

    def tearDown(self):
        os.chdir(self.cwd)
        self.env.stop()
        self.temp.cleanup()

    def write_tasks(self, tasks):
        (self.root / "config/instances/test-instance.json").write_text(json.dumps({"TaskItems": tasks}), encoding="utf-8")

    def test_exact_named_reference_and_no_cross_instance_fallback(self):
        self.assertEqual(read_daily_plan()[1]["display_name_override"], "午间方案")
        self.write_tasks([saved_daily("零点"), saved_daily("中午")])
        self.assertEqual(read_daily_plan("中午")[1]["display_name_override"], "中午")
        for name in ("", "不存在", "日常收尾"):
            with self.assertRaises(ValueError):
                read_daily_plan(name)
        self.write_tasks([saved_daily("中午"), saved_daily("中午")])
        with self.assertRaises(ValueError):
            read_daily_plan("中午")
        with patch.dict(os.environ, {"MFA_INSTANCE_ID": "../default"}):
            with self.assertRaises(ValueError):
                read_daily_plan()

    def test_mfa_remark_names_and_legacy_fallbacks(self):
        first, second = saved_daily("旧名称一"), saved_daily("旧名称二")
        first["remark"] = "日常收尾（零点）"
        second["remark"] = "日常收尾（中午）"
        self.write_tasks([first, second])
        self.assertEqual(read_daily_plan(first["remark"])[1], first)
        self.assertEqual(read_daily_plan(second["remark"])[1], second)
        for name in ("", "旧名称一", "日常收尾"):
            with self.assertRaises(ValueError):
                read_daily_plan(name)
        second["remark"] = first["remark"]
        self.write_tasks([first, second])
        with self.assertRaises(ValueError):
            read_daily_plan(first["remark"])
        for task, expected in (
            ({"remark": "备注", "display_name_override": "旧名", "label": "标签", "name": "名称"}, "备注"),
            ({"remark": "", "display_name_override": "旧名"}, "旧名"),
            ({"remark": "", "label": "标签", "name": "名称"}, "标签"),
            ({"name": "名称"}, "名称"),
        ):
            self.assertEqual(daily_task_name(task), expected)

    def test_legacy_romantic_checkbox_alias_is_exact_and_nonmutating(self):
        current = saved_daily(selected=["浪漫满屋祝福"])
        expected = compile_daily_options(INTERFACE, current)
        for selected in (["浪漫满屋"], ["浪漫满屋", "浪漫满屋祝福"]):
            task = saved_daily(selected=selected)
            before = copy.deepcopy(task)
            overrides = compile_daily_options(INTERFACE, task)
            self.assertEqual(overrides, expected)
            self.assertEqual(sum("DailyRoutineEnableRomanticHouse" in o for o in overrides), 1)
            self.assertEqual(task, before)
        for selected in ([], ["浪漫满屋旧版"]):
            task = saved_daily(selected=selected)
            if selected:
                with self.assertRaisesRegex(ValueError, "多选项已失效"):
                    compile_daily_options(INTERFACE, task)
            else:
                self.assertFalse(any("DailyRoutineEnableRomanticHouse" in o
                                     for o in compile_daily_options(INTERFACE, task)))

    def test_remark_and_legacy_choice_resolve_together(self):
        task = saved_daily(selected=["浪漫满屋", "浪漫满屋祝福", "每日免费礼包"])
        task.pop("display_name_override")
        task["remark"] = "日常收尾（零点）"
        self.write_tasks([task])
        interface, saved = read_daily_plan(task["remark"])
        ctx = Context()
        for override in compile_daily_options(interface, saved):
            ctx.override_pipeline(override)
        self.assertTrue(ctx.nodes["DailyRoutineEnableRomanticHouse"]["enabled"])
        self.assertTrue(ctx.nodes["DailyRoutineEnableFreeGift"]["enabled"])
        self.assertFalse(ctx.nodes["DailyRoutineEnableFishBaby"]["enabled"])
        self.assertEqual(read_daily_plan(task["remark"])[1], task)

    def test_selected_nested_inputs_and_nondefault_parameters(self):
        task = saved_daily(selected=["购买鱼食", "鱼宝乐园", "深海寻鱼（仅每日最多2次免费，立即返航）"])
        # Resolve the exact case name from the interface rather than an alias.
        sea = next(c["name"] for c in INTERFACE["option"]["日常收尾任务"]["cases"] if "深海寻鱼" in c["name"])
        task["option"][0]["selected_cases"][-1] = sea
        task["option"][0]["sub_options"] = [
            {"name": "购买廉价鱼食袋数", "data": {"袋数": "23", "普通袋数": "4", "高级袋数": "0"}},
            {"name": "鱼宝玩耍设置", "index": 0, "sub_options": [{"name": "1号宝宝玩耍方式", "index": 2}]},
        ]
        task["option"].extend([{"name": "金海豚奖励优先级", "index": 1}, {"name": "钓鱼地点", "index": 2},
                              {"name": "乐队鱼乐章", "index": 3}])
        ctx = Context()
        for override in compile_daily_options(INTERFACE, task):
            ctx.override_pipeline(override)
        self.assertTrue(ctx.nodes["DailyRoutineEnableSeaDive"]["enabled"])
        self.assertFalse(ctx.nodes["DailyRoutineEnableFreeGift"]["enabled"])
        self.assertEqual(ctx.nodes["BuyFishFoodStartAtDetail"]["custom_action_param"], {"bags": 23, "normal_bags": 4, "high_bags": 0})
        self.assertEqual(ctx.nodes["GoldenDolphinTask"]["custom_action_param"]["reward_priority"], "heart")
        self.assertNotEqual(ctx.nodes["FishingLocationRouter"]["next"], BASE["FishingLocationRouter"]["next"])
        self.assertEqual(ctx.nodes["FishBabyPreference1"]["custom_action_param"]["preference"], "SING")
        # Inactive suboptions saved in the UI must not leak into an unselected case.
        task["option"][0]["selected_cases"] = []
        keys = {name for override in compile_daily_options(INTERFACE, task) for name in override}
        self.assertNotIn("BuyFishFoodStartAtDetail", keys)
        self.assertNotIn("FishBabyPreference1", keys)

    def test_defaults_empty_checkbox_and_invalid_choices(self):
        task = saved_daily()
        self.assertFalse(any(name.startswith("DailyRoutineEnable") for o in compile_daily_options(INTERFACE, task) for name in o))
        task["option"] = []
        self.assertTrue(any("DailyRoutineEnableBandFish" in o for o in compile_daily_options(INTERFACE, task)))
        task["option"] = [{"name": "日常收尾任务", "selected_cases": ["领取活动体力（酿月食香）", "每日免费礼包"]}]
        overrides = compile_daily_options(INTERFACE, task)
        self.assertTrue(any("DailyRoutineEnableFreeGift" in o for o in overrides))
        self.assertFalse(any("DailyRoutineEnableActivityEnergy" in o for o in overrides))
        task["option"] = [{"name": "日常收尾任务", "selected_cases": ["已删除的功能"]}]
        with self.assertRaises(ValueError):
            compile_daily_options(INTERFACE, task)
        task["option"] = [{"name": "金海豚奖励优先级", "index": 100}]
        with self.assertRaises(ValueError):
            compile_daily_options(INTERFACE, task)

    def test_scheduled_isolation_return_stack_and_failure(self):
        ctx = Context()
        ctx.nodes["DailyRoutineEnableFreeGift"]["enabled"] = True
        ctx.nodes["GoldenDolphinTask"]["custom_action_param"] = {"reward_priority": "coin"}
        original = copy.deepcopy(ctx.nodes)
        hangup_schedule_state["resume_stack"] = ["patrol"]
        self.assertTrue(InitHangupScheduledDailyAction().run(ctx, arg({"resume_to": "friend_gem"})))
        self.assertEqual(ctx.nodes, original)
        self.assertEqual(hangup_schedule_state["resume_stack"], ["patrol", "friend_gem"])
        child = ctx.runs[0][1]
        self.assertFalse(child["DailyRoutineEnableFreeGift"]["enabled"])
        self.assertEqual(child["GoldenDolphinTask"]["custom_action_param"]["reward_priority"], "xp")
        self.assertFalse(daily_routine_state["active"])
        ctx.fail_child = True
        self.assertFalse(InitHangupScheduledDailyAction().run(ctx, arg({"resume_to": "patrol"})))
        self.assertFalse(daily_routine_state["active"])
        self.assertEqual(hangup_schedule_state["resume_stack"], [])
        ctx.fail_child = False
        ctx.stop_child = True
        self.assertFalse(InitHangupScheduledDailyAction().run(ctx, arg({"resume_to": "patrol"})))
        self.assertEqual(hangup_schedule_state["resume_stack"], [])

    def test_write_failure_and_missing_reference_do_not_start_or_mark_attempt(self):
        ctx = Context()
        with patch.object(local_state, "save_local_state", return_value=False):
            self.assertFalse(InitHangupScheduledDailyAction().run(ctx, arg()))
        self.assertFalse(ctx.runs)
        self.assertIsNone(hangup_schedule_state["noon_daily_last_date"])
        self.write_tasks([])
        self.assertFalse(InitHangupScheduledDailyAction().run(ctx, arg()))
        self.assertFalse(ctx.runs)
        self.assertIsNone(hangup_schedule_state["noon_daily_last_date"])

    def test_completed_same_config_only_skips_and_persists(self):
        ctx = Context()
        task = saved_daily(selected=["每日免费礼包"])
        for override in compile_daily_options(INTERFACE, task):
            ctx.override_pipeline(override)
        self.assertTrue(InitDailyRoutineAction().run(ctx, arg()))
        signature = daily_routine_state["config_signature"]
        self.assertFalse(local_state.daily_plan_completed_today(signature))
        daily_routine_state.update(step="ALL_DONE", queue=[])
        self.assertTrue(DailyRoutineFinishAction().run(ctx, arg()))
        self.assertTrue(local_state.daily_plan_completed_today(signature))
        self.assertIsNone(hangup_schedule_state["noon_daily_last_date"])
        self.assertTrue(InitDailyRoutineAction().run(ctx, arg({"scheduled_run": True})))
        self.assertEqual(daily_routine_state["step"], "ALL_DONE")
        ctx.nodes["GoldenDolphinTask"]["custom_action_param"] = {"reward_priority": "gem"}
        self.assertTrue(InitDailyRoutineAction().run(ctx, arg({"scheduled_run": True})))
        self.assertEqual(daily_routine_state["step"], "FREE_GIFT")

    def test_failed_stopped_and_next_queue_lifecycle_unblocks_dates(self):
        sink = DailyTaskLifecycleSink()
        for event in (NotificationType.Failed, NotificationType.Succeeded, NotificationType.Starting):
            daily_routine_state.update(active=True, step="FISH_BABY", queue=["PRINCESS_TASK"])
            hangup_schedule_state["resume_stack"] = ["patrol"]
            sink.on_tasker_task(None, event, SimpleNamespace(task_id=1))
            self.assertFalse(daily_routine_state["active"])
            self.assertEqual(daily_routine_state["outcome"], "INTERRUPTED")
            self.assertFalse(hangup_schedule_state["resume_stack"])
            self.assertIsNotNone(CheckHangupNoonDailyDueReco().analyze(None, arg({"enabled": True, "now": "2026-10-15T12:20:00"})))
            self.assertIsNotNone(CheckHangupFriendGemDueReco().analyze(None, arg({"enabled": True, "now": "2026-10-15T22:00:00"})))

    def test_native_nested_context_and_task_events_without_device(self):
        import numpy as np
        from maa.controller import CustomController
        from maa.custom_action import CustomAction
        from maa.library import Library
        from maa.resource import Resource
        from maa.tasker import Tasker
        from agent.my_reco import CheckDailyRoutineStepReco
        from agent.my_action import FailTaskAction

        Library.open(Library.framework_libpath.parent, agent_server=False)

        class Controller(CustomController):
            def connect(self): return True
            def request_uuid(self): return "offline-daily-plan"
            def get_features(self): return 0
            def screencap(self): return np.zeros((720, 1280, 3), dtype=np.uint8)

        events = []

        class Sink(DailyTaskLifecycleSink):
            def on_tasker_task(self, tasker, noti_type, detail):
                events.append((detail.entry, noti_type))
                super().on_tasker_task(tasker, noti_type, detail)

        class ProbeReturn(CustomAction):
            def run(self, context, argv):
                # The child must not overwrite the parent's selected reward or navigation.
                node = context.get_node_data("GoldenDolphinTask")
                assert node["action"]["param"]["custom_action_param"]["reward_priority"] == "coin"
                assert not daily_routine_state["active"]
                assert hangup_schedule_state["resume_stack"] == ["patrol"]
                return True

        resource = Resource()
        self.assertTrue(resource.post_bundle(ROOT / "assets/resource").wait().succeeded)
        for name, action in (("InitHangupScheduledDailyAction", InitHangupScheduledDailyAction()),
                             ("InitDailyRoutineAction", InitDailyRoutineAction()),
                             ("DailyRoutineFinishAction", DailyRoutineFinishAction()),
                             ("FailTaskAction", FailTaskAction()), ("NativeProbeReturn", ProbeReturn())):
            self.assertTrue(resource.register_custom_action(name, action))
        self.assertTrue(resource.register_custom_recognition("CheckDailyRoutineStepReco", CheckDailyRoutineStepReco()))
        globals_ = [name for name in BASE if name.startswith("Global")]
        # Synthetic gates replace vision only in this offline test; no real controller.
        self.assertTrue(resource.override_pipeline({
            **{name: {"enabled": False} for name in globals_},
            "HangupDailyOnTank": {"recognition": "DirectHit"},
        }))
        controller = Controller()
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        tasker.add_sink(Sink())
        self.assertTrue(tasker.bind(resource, controller))
        # Simulate MFA's manual task parameter list with the same saved plan.
        manual_overrides = compile_daily_options(INTERFACE, saved_daily()) + [
            {"DailyRoutineStepAllDone": {"next": ["DailyRoutineStandaloneDone"]}}
        ]
        self.assertTrue(tasker.post_task("DailyRoutineTask", manual_overrides).wait().succeeded)
        manual_signature = daily_routine_state["config_signature"]
        self.assertTrue(local_state.daily_plan_completed_today(manual_signature))
        events.clear()
        pipeline = {
            "NativeScheduled": {"recognition": "DirectHit", "action": "Custom", "custom_action": "InitHangupScheduledDailyAction",
                                "custom_action_param": {"resume_to": "patrol"}, "next": ["NativeProbeReturn"]},
            "NativeProbeReturn": {"recognition": "DirectHit", "action": "Custom", "custom_action": "NativeProbeReturn"},
            "GoldenDolphinTask": {"custom_action_param": {"reward_priority": "coin"}},
        }
        self.assertTrue(tasker.post_task("NativeScheduled", pipeline).wait().succeeded)
        self.assertEqual(events, [("NativeScheduled", NotificationType.Starting), ("NativeScheduled", NotificationType.Succeeded)])
        self.assertFalse(daily_routine_state["active"])
        self.assertFalse(hangup_schedule_state["resume_stack"])
        self.assertEqual(daily_routine_state["config_signature"], manual_signature)
        self.assertEqual(daily_routine_state["tasks"]["FreeGift"]["status"], "SKIPPED")

    def test_real_agent_process_lifecycle_and_reference_without_device(self):
        """Exercise main.py's sink registration and the real cross-process path."""
        import subprocess
        import numpy as np
        from maa.agent_client import AgentClient
        from maa.controller import CustomController
        from maa.library import Library
        from maa.resource import Resource
        from maa.tasker import Tasker

        Library.open(Library.framework_libpath.parent, agent_server=False)

        class Controller(CustomController):
            def connect(self): return True
            def request_uuid(self): return "offline-agent-daily-plan"
            def get_features(self): return 0
            def screencap(self): return np.zeros((720, 1280, 3), dtype=np.uint8)

        resource = Resource()
        self.assertTrue(resource.post_bundle(ROOT / "assets/resource").wait().succeeded)
        self.assertTrue(resource.override_pipeline({
            **{name: {"enabled": False} for name in BASE if name.startswith("Global")},
            "HangupDailyOnTank": {"recognition": "DirectHit"},
        }))
        controller = Controller()
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        client = AgentClient()
        self.assertTrue(client.bind(resource))
        self.assertTrue(client.register_sink(resource, controller, tasker))
        self.assertTrue(client.set_timeout(10000))
        output_path = self.root / "agent-offline.log"
        with output_path.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "agent/main.py"), client.identifier],
                cwd=self.root, stdout=output, stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                self.assertTrue(client.connect())
                # Only synthetic DirectHit nodes: no game navigation, OCR or clicks.
                for terminal, action in (("NativeFail", "Custom"), ("NativeStop", "StopTask")):
                    overrides = {
                        "NativeDaily": {"recognition": "DirectHit", "action": "Custom", "custom_action": "InitDailyRoutineAction",
                                        "custom_action_param": {"free_gift": True}, "next": [terminal]},
                        terminal: {"recognition": "DirectHit", "action": action, "custom_action": "FailTaskAction"} if action == "Custom"
                                  else {"recognition": "DirectHit", "action": action},
                    }
                    job = tasker.post_task("NativeDaily", overrides).wait()
                    self.assertEqual(job.failed, action == "Custom")
                job = tasker.post_task("NativeReference", {
                    "NativeReference": {"recognition": "DirectHit", "action": "Custom", "custom_action": "InitHangupScheduledDailyAction",
                                        "custom_action_param": {"resume_to": "patrol"}},
                }).wait()
                self.assertTrue(job.succeeded)
            finally:
                client.disconnect()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)
        output = output_path.read_text(encoding="utf-8")
        self.assertGreaterEqual(output.count("队列任务已结束或停止；清理未完成上下文"), 2)
        self.assertIn("引用日常【午间方案】", output)


if __name__ == "__main__":
    unittest.main()
