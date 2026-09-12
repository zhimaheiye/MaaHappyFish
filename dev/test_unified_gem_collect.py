"""
统一鱼缸收宝石双模式 (IMAGE / SHAKE) 静态与契约单元测试
覆盖：
1. Pipeline 结构校验 (单缸、巡检、好友摸宝)
2. Interface 配置与契约校验
3. SetGemCollectModeAction 模式切换
4. CheckGemCollectModeReco 识别器分流
5. execute_shake_gem_collect_cycle 执行器 (S->W 交替、6次扫底、连续3次失败熔断、取消响应)
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.runtime_state import gem_collect_state
from agent.my_action import (
    GEM_SHAKE_CYCLES,
    GEM_SHAKE_SETTLE_DELAY_SECONDS,
    GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS,
    GEM_SHAKE_MAX_CONSECUTIVE_FAILURES,
    SWEEP_BOTTOM_BEGIN,
    SWEEP_BOTTOM_END,
    SWEEP_BOTTOM_DURATION_MS,
    SWEEP_BOTTOM_POST_DELAY_SECONDS,
    perform_fish_tank_bottom_sweep,
    execute_shake_gem_collect_cycle,
    SetGemCollectModeAction,
    UnifiedShakeGemCollectAction,
    FriendGemShakeAndAdvanceAction,
)
from agent.my_reco import CheckGemCollectModeReco


class TestUnifiedGemCollectPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "assets/resource/pipeline/collect_fish.json"), "r", encoding="utf-8") as f:
            cls.collect_pipeline = json.load(f)
        with open(os.path.join(ROOT, "assets/resource/pipeline/features/patrol.json"), "r", encoding="utf-8") as f:
            cls.patrol_pipeline = json.load(f)
        with open(os.path.join(ROOT, "assets/resource/pipeline/features/friend_gem.json"), "r", encoding="utf-8") as f:
            cls.friend_pipeline = json.load(f)

    def test_collect_fish_pipeline_structure(self):
        # 1. CollectFishTask entry node
        entry = self.collect_pipeline["CollectFishTask"]
        self.assertIn("CollectFishSetGemCollectMode", entry["next"])
        self.assertEqual(entry["next"][0], "CollectFishSetGemCollectMode")

        # 2. CollectFishSetGemCollectMode definition
        set_node = self.collect_pipeline["CollectFishSetGemCollectMode"]
        self.assertEqual(set_node["recognition"], "DirectHit")
        self.assertEqual(set_node["action"], "Custom")
        self.assertEqual(set_node["custom_action"], "SetGemCollectModeAction")
        self.assertEqual(set_node["custom_action_param"]["mode"], "IMAGE")

        # 3. ResumeHarvest next list has CollectFishShakeGem right before ClickFishBubble
        rh = self.collect_pipeline["ResumeHarvest"]
        shake_idx = rh["next"].index("CollectFishShakeGem")
        bubble_idx = rh["next"].index("ClickFishBubble")
        self.assertEqual(shake_idx + 1, bubble_idx)

        # 4. CollectFishShakeGem definition
        shake_node = self.collect_pipeline["CollectFishShakeGem"]
        self.assertEqual(shake_node["recognition"], "Custom")
        self.assertEqual(shake_node["custom_recognition"], "CheckGemCollectModeReco")
        self.assertEqual(shake_node["action"], "Custom")
        self.assertEqual(shake_node["custom_action"], "UnifiedShakeGemCollectAction")
        self.assertIn("ResumeHarvest", shake_node["next"])

    def test_patrol_pipeline_structure(self):
        # 1. PatrolTask entry node
        entry = self.patrol_pipeline["PatrolTask"]
        self.assertIn("PatrolSetGemCollectMode", entry["next"])
        self.assertEqual(entry["next"][0], "PatrolSetGemCollectMode")

        # 2. PatrolSetGemCollectMode definition
        set_node = self.patrol_pipeline["PatrolSetGemCollectMode"]
        self.assertEqual(set_node["recognition"], "DirectHit")
        self.assertEqual(set_node["action"], "Custom")
        self.assertEqual(set_node["custom_action"], "SetGemCollectModeAction")
        self.assertEqual(set_node["custom_action_param"]["mode"], "IMAGE")

        # 3. PatrolCollectTank1/2/3 next list has ShakeGem before Bubble
        for tank in (1, 2, 3):
            tank_node = self.patrol_pipeline[f"PatrolCollectTank{tank}"]
            shake_name = f"PatrolCollectTank{tank}ShakeGem"
            bubble_name = f"PatrolCollectTank{tank}Bubble"
            self.assertIn(shake_name, tank_node["next"])
            self.assertIn(bubble_name, tank_node["next"])
            self.assertEqual(
                tank_node["next"].index(shake_name) + 1,
                tank_node["next"].index(bubble_name),
            )

            # Node definition check
            shake_def = self.patrol_pipeline[shake_name]
            self.assertEqual(shake_def["recognition"], "Custom")
            self.assertEqual(shake_def["custom_recognition"], "CheckGemCollectModeReco")
            self.assertEqual(shake_def["action"], "Custom")
            self.assertEqual(shake_def["custom_action"], "UnifiedShakeGemCollectAction")

            expected_next = f"PatrolOpenPickerAfterTank{tank}" if tank < 3 else "PatrolOpenManagement"
            self.assertIn(expected_next, shake_def["next"])

    def test_patrol_advance_only_after_shake_action_succeeded(self):
        """验证 Patrol 切缸节点必须作为 ShakeGem 节点的 next，严格依赖 Action 执行成功"""
        for tank in (1, 2, 3):
            shake_name = f"PatrolCollectTank{tank}ShakeGem"
            shake_def = self.patrol_pipeline[shake_name]
            expected_next = f"PatrolOpenPickerAfterTank{tank}" if tank < 3 else "PatrolOpenManagement"
            # 必须在 next 列表中，且该节点自身只在 Action 返回 True 后由 MaaFW 触发 next
            self.assertEqual(shake_def["next"][-1], expected_next)
            # 无不受控的旁路直接跳转
            self.assertEqual(shake_def["action"], "Custom")
            self.assertEqual(shake_def["custom_action"], "UnifiedShakeGemCollectAction")

    def test_image_mode_pipeline_elements_untouched(self):
        """证明 IMAGE 模式的关键气泡模板、阈值与扫底参数字节级未被破坏"""
        for tank in (1, 2, 3):
            bubble_name = f"PatrolCollectTank{tank}Bubble"
            bubble_node = self.patrol_pipeline[bubble_name]
            self.assertEqual(bubble_node["recognition"], "TemplateMatch")
            self.assertEqual(bubble_node["template"], "金币气泡.png")
            self.assertEqual(bubble_node["threshold"], 0.75)
            self.assertEqual(bubble_node["roi"], [0, 100, 1280, 560])
            self.assertEqual(bubble_node["action"], "Click")

            sweep_name = f"PatrolSweepTank{tank}AfterBubble"
            sweep_node = self.patrol_pipeline[sweep_name]
            self.assertEqual(sweep_node["action"], "Swipe")
            self.assertEqual(sweep_node["begin"], [221, 663])
            self.assertEqual(sweep_node["end"], [1007, 663])
            self.assertEqual(sweep_node["duration"], 250)

    def test_friend_gem_pipeline_structure(self):
        # 1. FriendGemTask entry node
        entry = self.friend_pipeline["FriendGemTask"]
        self.assertIn("FriendGemSetGemCollectMode", entry["next"])
        self.assertEqual(entry["next"][0], "FriendGemSetGemCollectMode")

        # 2. FriendGemSetGemCollectMode definition
        set_node = self.friend_pipeline["FriendGemSetGemCollectMode"]
        self.assertEqual(set_node["recognition"], "DirectHit")
        self.assertEqual(set_node["action"], "Custom")
        self.assertEqual(set_node["custom_action"], "SetGemCollectModeAction")
        self.assertEqual(set_node["custom_action_param"]["mode"], "IMAGE")

        # 3. FriendGemFriendRouter next list has FriendGemShakeGem before FriendGemCollectBubble
        router = self.friend_pipeline["FriendGemFriendRouter"]
        shake_idx = router["next"].index("FriendGemShakeGem")
        bubble_idx = router["next"].index("FriendGemCollectBubble")
        self.assertEqual(shake_idx + 1, bubble_idx)

        # 4. FriendGemShakeGem definition
        shake_node = self.friend_pipeline["FriendGemShakeGem"]
        self.assertEqual(shake_node["recognition"], "Custom")
        self.assertEqual(shake_node["custom_recognition"], "CheckGemCollectModeReco")
        self.assertEqual(shake_node["action"], "Custom")
        self.assertEqual(shake_node["custom_action"], "FriendGemShakeAndAdvanceAction")
        self.assertIn("FriendGemNextFriend", shake_node["next"])


class TestUnifiedGemCollectInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "assets/interface.json"), "r", encoding="utf-8") as f:
            cls.interface = json.load(f)

    def test_option_definition_and_task_bindings(self):
        self.assertIn("收宝石方式", self.interface["option"])
        opt = self.interface["option"]["收宝石方式"]
        self.assertEqual(opt["type"], "select")
        self.assertEqual(opt["default_case"], "图像识别")
        case_names = [c["name"] for c in opt["cases"]]
        self.assertEqual(case_names, ["图像识别", "MuMu摇晃"])

        # Check bindings
        tasks_map = {t["entry"]: t for t in self.interface["task"]}
        for entry_name in ("CollectFishTask", "PatrolTask", "FriendGemTask"):
            self.assertIn(entry_name, tasks_map)
            self.assertIn("收宝石方式", tasks_map[entry_name].get("option", []))


class TestUnifiedGemCollectAgentLogic(unittest.TestCase):
    def setUp(self):
        gem_collect_state["mode"] = "IMAGE"

    def test_set_gem_collect_mode_action(self):
        action = SetGemCollectModeAction()
        mock_context = MagicMock()

        # Set to SHAKE
        arg_shake = MagicMock()
        arg_shake.custom_action_param = json.dumps({"mode": "SHAKE"})
        self.assertTrue(action.run(mock_context, arg_shake))
        self.assertEqual(gem_collect_state["mode"], "SHAKE")

        # Set to IMAGE
        arg_image = MagicMock()
        arg_image.custom_action_param = json.dumps({"mode": "IMAGE"})
        self.assertTrue(action.run(mock_context, arg_image))
        self.assertEqual(gem_collect_state["mode"], "IMAGE")

        # Invalid fallback to IMAGE
        arg_invalid = MagicMock()
        arg_invalid.custom_action_param = json.dumps({"mode": "UNKNOWN"})
        self.assertTrue(action.run(mock_context, arg_invalid))
        self.assertEqual(gem_collect_state["mode"], "IMAGE")

    def test_check_gem_collect_mode_reco(self):
        reco = CheckGemCollectModeReco()
        mock_context = MagicMock()

        # When mode is IMAGE: reco returns None (falls through to bubble click)
        gem_collect_state["mode"] = "IMAGE"
        arg = MagicMock()
        arg.custom_recognition_param = ""
        self.assertIsNone(reco.analyze(mock_context, arg))

        # When mode is SHAKE: reco returns (0, 0, 10, 10)
        gem_collect_state["mode"] = "SHAKE"
        hit = reco.analyze(mock_context, arg)
        self.assertEqual(hit, (0, 0, 10, 10))

        # Direct param override
        arg_param = MagicMock()
        arg_param.custom_recognition_param = json.dumps({"mode": "SHAKE"})
        gem_collect_state["mode"] = "IMAGE"
        self.assertEqual(reco.analyze(mock_context, arg_param), (0, 0, 10, 10))


class TestUnifiedGemCollectExecutor(unittest.TestCase):
    def test_constants_and_parameter_values(self):
        """测试调参常量集中定义与合理范围"""
        self.assertEqual(GEM_SHAKE_CYCLES, 5)
        self.assertGreaterEqual(GEM_SHAKE_SETTLE_DELAY_SECONDS, 1.2)
        self.assertGreaterEqual(GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS, 1.2)
        self.assertEqual(GEM_SHAKE_MAX_CONSECUTIVE_FAILURES, 3)

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    def test_strict_alternating_sequence_and_final_sweep_before_return(self, mock_get_vm, mock_shake, mock_sleep):
        """
        验证严格时序 (以 cycles=3 为例):
        shake 1 -> wait -> sweep 1
        -> shake 2 -> wait -> sweep 2
        -> shake 3 -> wait -> sweep 3
        -> final_wait -> final_sweep
        并且 final_sweep 完成前函数绝不返回 True。
        """
        mock_get_vm.return_value = ("MuMuManager.exe", 0)

        events = []
        return_called = [False]

        def on_shake(*args, **kwargs):
            events.append("shake")
            return True

        def on_sleep(sec):
            events.append(f"sleep_{sec:.2f}")

        def on_swipe(*args, **kwargs):
            events.append("sweep")
            # 确认在执行 sweep 时函数尚未结束返回
            self.assertFalse(return_called[0])
            mock_job = MagicMock()
            return mock_job

        mock_shake.side_effect = on_shake
        mock_sleep.side_effect = on_sleep

        mock_ctrl = MagicMock()
        mock_ctrl.post_swipe.side_effect = on_swipe

        mock_context = MagicMock()
        mock_context.tasker.stopping = False
        mock_context.tasker.running = True

        res = execute_shake_gem_collect_cycle(
            mock_context, mock_ctrl, cycles=3, delay_between=0.2, final_delay=0.3
        )
        return_called[0] = True
        self.assertTrue(res)

        # 检验严格执行序列: 3 组 (shake -> 沉降等待 -> sweep -> sweep后置延时) + 1 组 final (最终沉降等待 -> sweep -> sweep后置延时)
        # cycles=3, delay_between=0.2 (2 steps of 0.10s sleep), final_delay=0.3 (3 steps of 0.10s sleep), sweep post_delay=0.12s
        expected_events = [
            "shake", "sleep_0.10", "sleep_0.10", "sweep", f"sleep_{SWEEP_BOTTOM_POST_DELAY_SECONDS:.2f}",
            "shake", "sleep_0.10", "sleep_0.10", "sweep", f"sleep_{SWEEP_BOTTOM_POST_DELAY_SECONDS:.2f}",
            "shake", "sleep_0.10", "sleep_0.10", "sweep", f"sleep_{SWEEP_BOTTOM_POST_DELAY_SECONDS:.2f}",
            "sleep_0.10", "sleep_0.10", "sleep_0.10", "sweep", f"sleep_{SWEEP_BOTTOM_POST_DELAY_SECONDS:.2f}",
        ]
        self.assertEqual(events, expected_events)

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    def test_circuit_breaker_on_three_consecutive_failures(self, mock_get_vm, mock_shake, mock_sleep):
        mock_get_vm.return_value = ("MuMuManager.exe", 0)
        mock_shake.return_value = False

        mock_ctrl = MagicMock()
        mock_ctrl.post_swipe.return_value = MagicMock()

        mock_context = MagicMock()
        mock_context.tasker.stopping = False
        mock_context.tasker.running = True

        res = execute_shake_gem_collect_cycle(mock_context, mock_ctrl, cycles=5, delay_between=0.1)
        self.assertFalse(res)
        self.assertEqual(mock_shake.call_count, GEM_SHAKE_MAX_CONSECUTIVE_FAILURES)

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    def test_cancellation_before_shake(self, mock_get_vm, mock_shake, mock_sleep):
        """任务在 shake 启动前取消"""
        mock_get_vm.return_value = ("MuMuManager.exe", 0)
        mock_shake.return_value = True

        mock_ctrl = MagicMock()
        mock_ctrl.post_swipe.return_value = MagicMock()

        mock_context = MagicMock()
        mock_context.tasker.stopping = True
        mock_context.tasker.running = False

        res = execute_shake_gem_collect_cycle(mock_context, mock_ctrl, cycles=5, delay_between=0.1)
        self.assertFalse(res)
        self.assertEqual(mock_shake.call_count, 0)
        self.assertEqual(mock_ctrl.post_swipe.call_count, 0)

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    def test_cancellation_during_settle_wait(self, mock_get_vm, mock_shake, mock_sleep):
        """在第一次 shake 后的沉降等待阶段触发取消，立即中断不执行后续 sweep"""
        mock_get_vm.return_value = ("MuMuManager.exe", 0)
        mock_shake.return_value = True

        mock_ctrl = MagicMock()
        mock_ctrl.post_swipe.return_value = MagicMock()

        mock_context = MagicMock()
        mock_context.tasker.stopping = False
        mock_context.tasker.running = True

        def cancel_on_sleep(sec):
            mock_context.tasker.stopping = True
            mock_context.tasker.running = False

        mock_sleep.side_effect = cancel_on_sleep

        res = execute_shake_gem_collect_cycle(mock_context, mock_ctrl, cycles=5, delay_between=0.2)
        self.assertFalse(res)
        self.assertEqual(mock_shake.call_count, 1)
        # 取消后不应执行 sweep
        self.assertEqual(mock_ctrl.post_swipe.call_count, 0)

    @patch("agent.my_action.time.sleep", return_value=None)
    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    def test_cancellation_during_final_settle_wait(self, mock_get_vm, mock_shake, mock_sleep):
        """在所有 shake 完成后的最终沉降等待阶段触发取消，不执行最后的补刀 sweep"""
        mock_get_vm.return_value = ("MuMuManager.exe", 0)
        mock_shake.return_value = True

        mock_ctrl = MagicMock()
        mock_ctrl.post_swipe.return_value = MagicMock()

        mock_context = MagicMock()
        mock_context.tasker.stopping = False
        mock_context.tasker.running = True

        sleep_count = [0]
        def cancel_at_final_sleep(sec):
            sleep_count[0] += 1
            # 2 个 cycle，每个 cycle 包含 1 次沉降 sleep(0.1) 和 1 次 sweep 后的 post_delay sleep(0.12)
            # 共 4 次 sleep。第 5 次 sleep 为进入 final 沉降等待时的第 1 次 sleep
            if sleep_count[0] >= 5:
                mock_context.tasker.stopping = True
                mock_context.tasker.running = False

        mock_sleep.side_effect = cancel_at_final_sleep

        # cycles=2, delay_between=0.1 (1 sleep per cycle -> 2 sleeps), final_delay=0.2
        res = execute_shake_gem_collect_cycle(
            mock_context, mock_ctrl, cycles=2, delay_between=0.1, final_delay=0.2
        )
        self.assertFalse(res)
        self.assertEqual(mock_shake.call_count, 2)
        # 只执行了 2 次普通 sweep，最终 sweep 因取消被拦截，总数仍为 2（而不是 3）
        self.assertEqual(mock_ctrl.post_swipe.call_count, 2)


if __name__ == "__main__":
    unittest.main()

