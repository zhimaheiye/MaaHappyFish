"""
dev/test_shake_gem_collect_test.py
摇一摇收宝石（测试）实验任务独立性与动作逻辑离线自动化测试套件
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent.my_action import (
    SHAKE_GEM_TEST_COUNT,
    SHAKE_GEM_TEST_INTERVAL_SECONDS,
    SHAKE_GEM_MAX_CONSECUTIVE_FAILURES,
    ShakeGemCollectAction,
    ShakeGemCollectDoneAction,
)


class TestShakeGemCollectTaskStructure(unittest.TestCase):
    """测试实验任务结构独立性与原收宝石逻辑完整性"""

    def setUp(self):
        self.collect_fish_path = REPO_ROOT / "assets" / "resource" / "pipeline" / "collect_fish.json"
        self.patrol_path = REPO_ROOT / "assets" / "resource" / "pipeline" / "features" / "patrol.json"
        self.test_pipeline_path = (
            REPO_ROOT / "assets" / "resource" / "pipeline" / "features" / "shake_gem_collect_test.json"
        )
        self.interface_paths = [
            REPO_ROOT / "assets" / "interface.json",
            REPO_ROOT / "client" / "interface.json",
            REPO_ROOT / "client_avalonia" / "interface.json",
        ]

    def test_original_collect_fish_pipeline_intact(self):
        """确认原单缸收鱼 Pipeline 未被修改/破坏"""
        self.assertTrue(self.collect_fish_path.exists())
        with open(self.collect_fish_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("CollectFishTask", data)
        self.assertIn("ClickFishBubble", data)
        self.assertIn("SweepFishTankBottomAfterBubble", data)

        bubble_node = data["ClickFishBubble"]
        self.assertEqual(bubble_node.get("recognition"), "TemplateMatch")
        self.assertEqual(bubble_node.get("template"), "金币气泡.png")
        self.assertEqual(bubble_node.get("action"), "Click")
        self.assertEqual(bubble_node.get("next"), ["SweepFishTankBottomAfterBubble"])

        sweep_node = data["SweepFishTankBottomAfterBubble"]
        self.assertEqual(sweep_node.get("action"), "Swipe")
        self.assertEqual(sweep_node.get("begin"), [221, 663])
        self.assertEqual(sweep_node.get("end"), [1007, 663])
        self.assertEqual(sweep_node.get("duration"), 250)

    def test_original_patrol_pipeline_intact(self):
        """确认巡检收宝 Pipeline 未被破坏"""
        self.assertTrue(self.patrol_path.exists())
        with open(self.patrol_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("PatrolSweepTank1AfterBubble", data)
        sweep1 = data["PatrolSweepTank1AfterBubble"]
        self.assertEqual(sweep1.get("action"), "Swipe")
        self.assertEqual(sweep1.get("begin"), [221, 663])
        self.assertEqual(sweep1.get("end"), [1007, 663])
        self.assertEqual(sweep1.get("duration"), 250)

    def test_shake_gem_collect_test_pipeline_structure(self):
        """确认实验任务 Pipeline 规范完整且独立"""
        self.assertTrue(self.test_pipeline_path.exists())
        with open(self.test_pipeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 节点存在性
        self.assertIn("ShakeGemCollectTestTask", data)
        self.assertIn("ShakeGemCollectVerifyTank", data)
        self.assertIn("ShakeGemCollectActionNode", data)
        self.assertIn("ShakeGemCollectSweepBottom", data)
        self.assertIn("ShakeGemCollectTestDone", data)

        # 主鱼缸状态校验门禁
        verify_node = data["ShakeGemCollectVerifyTank"]
        self.assertEqual(verify_node.get("recognition"), "TemplateMatch")
        self.assertEqual(verify_node.get("template"), "主界面特征.png")
        self.assertEqual(verify_node.get("action"), "DoNothing")
        self.assertEqual(verify_node.get("next"), ["ShakeGemCollectActionNode"])

        # 动作节点
        action_node = data["ShakeGemCollectActionNode"]
        self.assertEqual(action_node.get("action"), "Custom")
        self.assertEqual(action_node.get("custom_action"), "ShakeGemCollectAction")
        self.assertEqual(action_node.get("next"), ["ShakeGemCollectSweepBottom"])

        # 底部滑动节点完全复用原参数
        sweep_node = data["ShakeGemCollectSweepBottom"]
        self.assertEqual(sweep_node.get("action"), "Swipe")
        self.assertEqual(sweep_node.get("begin"), [221, 663])
        self.assertEqual(sweep_node.get("end"), [1007, 663])
        self.assertEqual(sweep_node.get("duration"), 250)
        self.assertEqual(sweep_node.get("next"), ["ShakeGemCollectTestDone"])

        # 完成节点
        done_node = data["ShakeGemCollectTestDone"]
        self.assertEqual(done_node.get("custom_action"), "ShakeGemCollectDoneAction")

    def test_interface_json_registration(self):
        """验证三份 interface.json 注册该实验任务，且默认未勾选 (default_check: false)"""
        for p in self.interface_paths:
            self.assertTrue(p.exists(), f"Missing {p}")
            with open(p, "r", encoding="utf-8") as f:
                content = json.load(f)

            tasks = {t["entry"]: t for t in content.get("task", [])}
            self.assertIn("ShakeGemCollectTestTask", tasks, f"ShakeGemCollectTestTask missing in {p}")
            test_task = tasks["ShakeGemCollectTestTask"]
            self.assertEqual(test_task.get("name"), "摇一摇收宝石（测试）")
            self.assertFalse(test_task.get("default_check"), f"default_check must be False in {p}")


from types import SimpleNamespace


class TestShakeGemCollectActionLogic(unittest.TestCase):
    """测试 ShakeGemCollectAction 执行逻辑、中断与熔断"""

    def setUp(self):
        self.action = ShakeGemCollectAction()
        self.done_action = ShakeGemCollectDoneAction()

    def _make_context(self, vm_index=0, stopping=False, running=True, ctrl=...):
        """
        使用 SimpleNamespace 严格模拟 MaaFramework 真实 Context 属性层级：
        context
        └── tasker
            ├── controller
            ├── running
            └── stopping
        严禁 context 直接暴露 controller 属性，杜绝 Mock 自动生成掩盖真实 API 错误。
        """
        if ctrl is ...:
            real_ctrl = MagicMock()
            real_ctrl.info = json.dumps({
                "config": {
                    "extras": {
                        "mumu": {
                            "path": "D:/MuMuPlayer-12.0",
                            "index": vm_index,
                        }
                    }
                }
            })
        else:
            real_ctrl = ctrl

        tasker = SimpleNamespace(
            controller=real_ctrl,
            stopping=stopping,
            running=running,
        )
        ctx = SimpleNamespace(tasker=tasker)
        return ctx

    def test_mock_context_hierarchy_contract(self):
        """严格断言：测试用的 context 绝对不存在 controller 属性，只在 tasker 下存在"""
        ctx = self._make_context()
        self.assertFalse(hasattr(ctx, "controller"), "context 绝不能直接包含 controller 属性！")
        self.assertTrue(hasattr(ctx, "tasker"), "context 必须包含 tasker 属性")
        self.assertTrue(hasattr(ctx.tasker, "controller"), "context.tasker 必须包含 controller 属性")
        self.assertIsNotNone(ctx.tasker.controller)

    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    @patch("time.sleep")
    def test_shake_gem_normal_run(self, mock_sleep, mock_get_vm, mock_shake):
        """正常流程：连续摇晃 SHAKE_GEM_TEST_COUNT 次并成功返回"""
        mock_get_vm.return_value = (Path("D:/MuMuPlayer-12.0/nx_main/MuMuManager.exe"), 0)
        mock_shake.return_value = True

        ctx = self._make_context()
        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertTrue(res)
        self.assertEqual(mock_shake.call_count, SHAKE_GEM_TEST_COUNT)

    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    @patch("time.sleep")
    def test_shake_gem_regression_real_hierarchy_without_context_controller(
        self, mock_sleep, mock_get_vm, mock_shake
    ):
        """事故针对性回归测试：真实层级 context 下无 context.controller，必须不抛 AttributeError 且成功进入 shake"""
        mock_get_vm.return_value = (Path("D:/MuMuPlayer-12.0/nx_main/MuMuManager.exe"), 0)
        mock_shake.return_value = True

        ctx = self._make_context()
        self.assertFalse(hasattr(ctx, "controller"))

        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertTrue(res)
        self.assertEqual(mock_shake.call_count, SHAKE_GEM_TEST_COUNT)

    @patch("agent.my_action._run_mumu_shake")
    def test_shake_gem_regression_controller_none(self, mock_shake):
        """反向回归测试：context.tasker.controller 为 None 时安全返回 False，不调用 RPC"""
        ctx = self._make_context(ctrl=None)
        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertFalse(res)
        mock_shake.assert_not_called()

    @patch("agent.my_action._run_mumu_shake")
    def test_shake_gem_regression_tasker_none(self, mock_shake):
        """反向回归测试：context.tasker 为 None 时安全返回 False，不抛异常"""
        ctx = SimpleNamespace(tasker=None)
        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertFalse(res)
        mock_shake.assert_not_called()

    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    @patch("time.sleep")
    def test_shake_gem_param_override(self, mock_sleep, mock_get_vm, mock_shake):
        """自定义参数：允许覆盖 count 和 interval"""
        mock_get_vm.return_value = (Path("D:/MuMuPlayer-12.0/nx_main/MuMuManager.exe"), 0)
        mock_shake.return_value = True

        ctx = self._make_context()
        arg = MagicMock()
        arg.custom_action_param = json.dumps({"count": 3, "interval": 0.5})

        res = self.action.run(ctx, arg)
        self.assertTrue(res)
        self.assertEqual(mock_shake.call_count, 3)

    @patch("agent.my_action._get_mumu_manager_and_vm")
    def test_shake_gem_missing_mumu(self, mock_get_vm):
        """无法获取 MuMuManager 或 VM index 时安全返回 False"""
        mock_get_vm.return_value = (None, None)

        ctx = self._make_context()
        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertFalse(res)

    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    @patch("time.sleep")
    def test_shake_gem_cancellation(self, mock_sleep, mock_get_vm, mock_shake):
        """收到停止信号时提前终止循环"""
        mock_get_vm.return_value = (Path("D:/MuMuPlayer-12.0/nx_main/MuMuManager.exe"), 0)
        mock_shake.return_value = True

        ctx = self._make_context(stopping=True)
        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertFalse(res)
        mock_shake.assert_not_called()

    @patch("agent.my_action._run_mumu_shake")
    @patch("agent.my_action._get_mumu_manager_and_vm")
    @patch("time.sleep")
    def test_shake_gem_circuit_breaker(self, mock_sleep, mock_get_vm, mock_shake):
        """连续 3 次失败触发安全熔断"""
        mock_get_vm.return_value = (Path("D:/MuMuPlayer-12.0/nx_main/MuMuManager.exe"), 0)
        mock_shake.return_value = False

        ctx = self._make_context()
        arg = MagicMock()
        arg.custom_action_param = ""

        res = self.action.run(ctx, arg)
        self.assertFalse(res)
        self.assertEqual(mock_shake.call_count, SHAKE_GEM_MAX_CONSECUTIVE_FAILURES)

    def test_shake_gem_done_action(self):
        """测试完成动作"""
        ctx = self._make_context()
        arg = MagicMock()
        self.assertTrue(self.done_action.run(ctx, arg))


if __name__ == "__main__":
    unittest.main()

