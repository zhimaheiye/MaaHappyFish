#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Code-level contract checks for the 1280x720 MuMu ad workflow."""

import json
import unittest
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = ROOT / "assets" / "resource" / "pipeline" / "features" / "emulator_ads.json"
IMAGE_DIR = ROOT / "assets" / "resource" / "image"


class TestEmulatorAds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
        cls.interface = json.loads((ROOT / "assets" / "interface.json").read_text(encoding="utf-8"))

    def test_state_router_and_safe_clicks(self):
        self.assertEqual(
            self.pipeline["EmulatorAdRouter"]["next"],
            [
                "EmulatorAdRewardPopup",
                "EmulatorAdStopEnabled",
                "EmulatorAdStopDisabled",
                "EmulatorAdClosePage",
                "EmulatorAdCenter",
                "EmulatorAdWaitForClose",
            ],
        )
        expected_templates = {
            "EmulatorAdCenter": ("看视频赚大奖.png", "Click"),
            "EmulatorAdClosePage": ("看广告页面_关闭.png", "Custom"),
            "EmulatorAdStopEnabled": ("停止按钮_可点击.png", "Click"),
            "EmulatorAdStopDisabled": ("停止按钮_不可点击.png", "DoNothing"),
            "EmulatorAdRewardPopup": ("下一段视频_对号.png", "Custom"),
            "EmulatorAdContinue": ("下一段视频_对号.png", "Click"),
            "EmulatorAdCloseRewardAndDone": ("看广告页面_关闭.png", "Click"),
        }
        for node_name, (template, action) in expected_templates.items():
            node = self.pipeline[node_name]
            self.assertEqual(node["recognition"], "TemplateMatch")
            if isinstance(node["template"], list):
                self.assertIn(template, node["template"])
            else:
                self.assertEqual(node["template"], template)
            self.assertEqual(node["roi"], [0, 0, 1280, 720])
            self.assertEqual(node["threshold"], 0.8)
            self.assertEqual(node["action"], action)
            if action == "Click" and node_name != "EmulatorAdClosePage":
                self.assertNotIn("target", node)

    def test_cycle_state_is_shared_without_copying_agent_logic(self):
        task = self.pipeline["EmulatorAdTask"]
        self.assertEqual(task["custom_action"], "MobileAdResetStateAction")
        self.assertEqual(task["custom_action_param"], {"max_cycles": 3, "log_tag": "模拟器看广告"})
        self.assertEqual(self.pipeline["EmulatorAdMarkStarted"]["custom_action"], "MobileAdOnAdStartAction")
        self.assertEqual(self.pipeline["EmulatorAdRewardPopup"]["custom_action"], "MobileAdRecordRewardAction")
        limit = self.pipeline["EmulatorAdCheckContinueCondition"]
        self.assertEqual(limit["custom_recognition"], "MobileAdCheckCycleLimitReco")
        self.assertEqual(limit["next"], ["EmulatorAdCloseRewardAndDone"])
        self.assertEqual(self.pipeline["EmulatorAdContinue"]["next"], ["EmulatorAdMarkStarted"])
        self.assertEqual(self.pipeline["EmulatorAdClosePage"]["custom_action"], "EmulatorAdClosePageAction")
        self.assertEqual(self.pipeline["EmulatorAdClosePage"]["next"], ["EmulatorAdPostAdRouter"])
        # Post 双 Router 均可识别第二层落地页关闭（多层广告落地页支持）
        for router_name in ("EmulatorAdPostAdRouter", "EmulatorAdPostStopRouter"):
            router_next = self.pipeline[router_name]["next"]
            self.assertIn("EmulatorAdClosePage", router_next)
            self.assertEqual(router_next[0], "EmulatorAdRewardPopup", "转盘/奖励优先于关闭页")
        self.assertEqual(self.pipeline["EmulatorAdStopEnabled"]["next"], ["EmulatorAdPostStopRouter"])
        self.assertEqual(self.pipeline["EmulatorAdStopDisabled"]["next"], ["EmulatorAdPostStopRouter"])
        for node_name in ("EmulatorAdPostAdRouter", "EmulatorAdPostStopRouter"):
            self.assertEqual(
                self.pipeline[node_name]["next"],
                ["EmulatorAdRewardPopup", "EmulatorAdStopEnabled", "EmulatorAdStopDisabled", "EmulatorAdClosePage"],
            )
        self.assertEqual(self.pipeline["EmulatorAdCloseRewardAndDone"]["next"], ["EmulatorAdDone"])

    def test_user_templates_exist_and_stop_states_are_distinct(self):
        names = [
            "看视频赚大奖.png",
            "看广告页面_关闭.png",
            "停止按钮_可点击.png",
            "停止按钮_不可点击.png",
            "下一段视频_对号.png",
        ]
        images = {}
        for name in names:
            path = IMAGE_DIR / name
            self.assertTrue(path.is_file(), name)
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertIsNotNone(image, name)
            images[name] = image

        enabled = images["停止按钮_可点击.png"]
        disabled = images["停止按钮_不可点击.png"]
        self.assertEqual(enabled.shape, disabled.shape)
        score = float(cv2.matchTemplate(enabled, disabled, cv2.TM_CCOEFF_NORMED)[0, 0])
        self.assertLess(score, 0.8)

    def test_interface_exposes_emulator_task_and_shared_cycle_options(self):
        task = next(item for item in self.interface["task"] if item["entry"] == "EmulatorAdTask")
        self.assertEqual(task["name"], "模拟器看广告")
        self.assertEqual(task["option"], ["模拟器广告轮数"])

        option = self.interface["option"]["模拟器广告轮数"]
        expected_cycles = {"3 轮(默认测试)": 3, "5 轮": 5, "10 轮": 10, "一直运行": 0}
        for case in option["cases"]:
            count = expected_cycles[case["name"]]
            override = case["pipeline_override"]
            self.assertEqual(override["EmulatorAdTask"]["custom_action_param"]["max_cycles"], count)
            self.assertEqual(
                override["EmulatorAdTask"]["custom_action_param"]["log_tag"],
                "模拟器看广告",
            )
            self.assertEqual(
                override["EmulatorAdCheckContinueCondition"]["custom_recognition_param"]["max_cycles"],
                count,
            )

        # Phone ad UI remains intact and has no "一直运行"
        phone_opt = self.interface["option"]["手机广告轮数"]
        phone_cases = [c["name"] for c in phone_opt["cases"]]
        self.assertNotIn("一直运行", phone_cases)

    def test_external_ad_pipeline_is_isolated_from_game_popup_handlers(self):
        source = (ROOT / "dev" / "test_daily_sign_global.py").read_text(encoding="utf-8")
        self.assertIn('"emulator_ads.json"', source)

    def test_wait_node_and_skip_logic_contract(self):
        # Case 1: EmulatorAdWaitForClose must have long timeout
        wait_node = self.pipeline["EmulatorAdWaitForClose"]
        self.assertEqual(wait_node["recognition"], "DirectHit")
        self.assertEqual(wait_node["action"], "DoNothing")
        self.assertGreaterEqual(wait_node["timeout"], 80000)
        self.assertIn("EmulatorAdClosePage", wait_node["next"])
        # 2026-09-18: 长等待窗口耗尽后才允许固定位置兜底（不再直接 Abort）
        self.assertEqual(wait_node["on_error"], ["EmulatorAdCloseFixedFallback"])

        # Case 2: EmulatorAdClosePage must strictly wait for X template
        close_node = self.pipeline["EmulatorAdClosePage"]
        self.assertEqual(close_node["recognition"], "TemplateMatch")
        self.assertIn("看广告页面_关闭.png", close_node["template"])
        self.assertIn("看广告页面_关闭1.png", close_node["template"])
        self.assertEqual(close_node["order_by"], "Score")
        self.assertEqual(close_node["action"], "Custom")
        # 模板关闭仍是主路径：ClosePage 自己的 on_error 不得指向固定兜底
        self.assertEqual(close_node["on_error"], ["EmulatorAdAbort"])

        close_done_node = self.pipeline["EmulatorAdCloseRewardAndDone"]
        self.assertIn("看广告页面_关闭.png", close_done_node["template"])
        self.assertIn("看广告页面_关闭1.png", close_done_node["template"])
        self.assertEqual(close_done_node["order_by"], "Score")

        # Case 3: Strictly NO skip click logic
        pipeline_str = json.dumps(self.pipeline, ensure_ascii=False)
        self.assertNotIn("跳过", pipeline_str)

    def test_fixed_close_fallback_contract(self):
        """2026-09-18 固定坐标关闭兜底：模板优先、长等待超时后一次兜底、转盘门禁。"""
        pipeline = self.pipeline

        # 固定兜底节点契约：一次点击 [1230,29,25,21]，汇入与模板关闭相同的转盘门禁
        fallback = pipeline["EmulatorAdCloseFixedFallback"]
        self.assertEqual(fallback["recognition"], "DirectHit")
        self.assertEqual(fallback["action"], "Click")
        self.assertEqual(fallback["target"], [1230, 29, 25, 21])
        self.assertNotEqual(fallback.get("post_delay"), 0)
        self.assertEqual(fallback["next"], ["EmulatorAdPostAdRouter"])
        self.assertEqual(fallback["on_error"], ["EmulatorAdAbort"])
        self.assertNotIn("timeout", fallback)

        # FixedFallback 唯一入口是 WaitForClose 的 on_error（等待窗口耗尽），
        # 绝不挂在 ClosePage 上，也绝不在任何 next 列表里（单帧 miss 不可达）
        referrers = []
        for name, node in pipeline.items():
            if name == "EmulatorAdCloseFixedFallback":
                continue
            if "EmulatorAdCloseFixedFallback" in node.get("on_error", []):
                referrers.append(("on_error", name))
            if "EmulatorAdCloseFixedFallback" in node.get("next", []):
                referrers.append(("next", name))
        self.assertEqual(
            referrers, [("on_error", "EmulatorAdWaitForClose")],
            "FixedFallback 只能由 WaitForClose 长等待超时进入",
        )

        # 模板关闭与固定兜底汇入同一转盘门禁（PostAdRouter），不复制两套后续逻辑
        self.assertEqual(pipeline["EmulatorAdClosePage"]["next"], ["EmulatorAdPostAdRouter"])
        post_router = pipeline["EmulatorAdPostAdRouter"]
        self.assertEqual(
            post_router["next"],
            ["EmulatorAdRewardPopup", "EmulatorAdStopEnabled", "EmulatorAdStopDisabled", "EmulatorAdClosePage"],
        )
        self.assertEqual(post_router["on_error"], ["EmulatorAdAbort"])

    def test_fixed_close_fallback_semantics(self):
        """Case 1~5 语义场景（基于真实 Maa next-list / on_error 语义的拓扑推演）。"""
        pipeline = self.pipeline

        def business(node, key):
            return list(node.get(key, []))

        # Case 1/2：任一关闭模板命中 → 点击识别 bbox → PostAdRouter 转盘门禁，
        # FixedFallback 不在模板命中路径上
        close_page = pipeline["EmulatorAdClosePage"]
        self.assertEqual(business(close_page, "next"), ["EmulatorAdPostAdRouter"])
        self.assertNotIn("EmulatorAdCloseFixedFallback", business(close_page, "on_error"))

        # Case 3：整个等待窗口模板全 miss → WaitForClose on_error → FixedFallback
        # 恰好一次（其 next 为 PostAdRouter，本轮不再回到 WaitForClose）
        wait_node = pipeline["EmulatorAdWaitForClose"]
        self.assertEqual(business(wait_node, "next"), ["EmulatorAdClosePage"])
        self.assertEqual(business(wait_node, "on_error"), ["EmulatorAdCloseFixedFallback"])
        self.assertNotIn("EmulatorAdCloseFixedFallback", business(wait_node, "next"))
        # FixedFallback 自身不回环到 WaitForClose：每轮广告最多一次固定点击
        self.assertNotIn("EmulatorAdWaitForClose", business(fallback_node := pipeline["EmulatorAdCloseFixedFallback"], "next"))
        self.assertNotIn("EmulatorAdWaitForClose", business(fallback_node, "on_error"))

        # Case 4：固定点击后仍在广告页/未知页 → PostAdRouter 20s 内三候选全 miss
        # → on_error Abort 安全停止；无二次固定点击、无循环
        post_router = pipeline["EmulatorAdPostAdRouter"]
        self.assertEqual(post_router["on_error"], ["EmulatorAdAbort"])
        for cycle_node in ("EmulatorAdStopEnabled", "EmulatorAdStopDisabled", "EmulatorAdRewardPopup"):
            self.assertNotEqual(pipeline[cycle_node].get("on_error"), ["EmulatorAdCloseFixedFallback"])

        # Case 5：广告前半段（"跳过"阶段）WaitForClose 活跃等待中，
        # ClosePage 单帧 miss 只是 next-list 循环重试，FixedFallback 完全不可达
        all_next_refs = [
            name for name, node in pipeline.items()
            if "EmulatorAdCloseFixedFallback" in node.get("next", [])
        ]
        self.assertEqual(all_next_refs, [])

        # 一直运行兼容：兜底位于单轮广告内部流程，轮数链路（Reward→Continue→MarkStarted）
        # 不经过 FixedFallback 判断，第 N 轮使用兜底后仍正常进入下一轮
        self.assertEqual(pipeline["EmulatorAdContinue"]["next"], ["EmulatorAdMarkStarted"])
        self.assertEqual(pipeline["EmulatorAdMarkStarted"]["next"], ["EmulatorAdWaitForClose"])

    def test_consecutive_close_count_lifecycle(self):
        """多层关闭安全计数的完整生命周期：Task Init 清零 / 新广告清零 / 领奖清零。"""
        import sys
        if 'agent' not in sys.path:
            sys.path.append('agent')
        import my_action
        import runtime_state as _rts
        mobile_ad_state = _rts.mobile_ad_state
        from types import SimpleNamespace as _NS

        # 模拟上一轮遗留脏状态（连续关闭超限）
        mobile_ad_state["consecutive_close_count"] = 99
        reset = my_action.MobileAdResetStateAction()
        argv = _NS(custom_action_param='{"max_cycles": 0, "log_tag": "模拟器看广告"}')
        assert reset.run(None, argv) is True
        assert mobile_ad_state["consecutive_close_count"] == 0, (
            "任务重新启动必须清零连续关闭计数（任意合法状态接续的前提）"
        )

        # 模拟从 ClosePage 状态直接启动：第一次关闭 0 -> 1（不继承旧运行状态）
        close = my_action.EmulatorAdClosePageAction()
        ctrl = my_action if False else None

        class _Ctrl:
            def __init__(self):
                self.clicks = []

            def post_click(self, x, y):
                self.clicks.append((x, y))

                class _J:
                    def wait(self):
                        return self

                return _J()

        class _Tasker:
            controller = None

        class _Ctx:
            tasker = None

        ctx = _Ctx()
        ctx.tasker = _Tasker()
        ctx.tasker.controller = _Ctrl()
        box = [1229, 28, 29, 21]
        argv_close = _NS(box=box)
        assert close.run(ctx, argv_close) is True
        assert mobile_ad_state["consecutive_close_count"] == 1
        assert ctx.tasker.controller.clicks == [(1243, 38)]
        print("[PASS] Reset 清零 + 从 ClosePage 直接启动：首次关闭 0 -> 1，不继承旧状态")

        # 连续关闭超过上限 -> return False（不再点击同一 X 链）
        for _ in range(3):
            assert close.run(ctx, argv_close) is True
        assert mobile_ad_state["consecutive_close_count"] == 4
        assert close.run(ctx, argv_close) is False, "超过上限后必须拒绝继续关闭"
        self.assertEqual(len(ctx.tasker.controller.clicks), 5, "超过上限的那次点击已发出，随后拒绝继续")
        print("[PASS] 连续关闭超过上限（>4）：拒绝继续点击同一 X 链")

        # OnAdStart / RecordReward 重置
        mobile_ad_state["consecutive_close_count"] = 3
        assert my_action.MobileAdOnAdStartAction().run(None, _NS()) is True
        assert mobile_ad_state["consecutive_close_count"] == 0
        mobile_ad_state["consecutive_close_count"] = 3
        reward = my_action.MobileAdRecordRewardAction()
        reward.run(None, _NS(custom_action_param="{}"))
        assert mobile_ad_state["consecutive_close_count"] == 0
        print("[PASS] OnAdStart / RecordReward 均重置连续关闭计数")

    def test_cycle_limit_reco_zero_logic(self):
        import sys
        if 'agent' not in sys.path:
            sys.path.append('agent')
        from my_reco import MobileAdCheckCycleLimitReco
        from maa.context import Context
        from maa.custom_recognition import CustomRecognition

        class _FakeArg:
            def __init__(self, p):
                self.custom_recognition_param = p

        class _FakeContext(Context):
            pass

        import my_reco
        reco = MobileAdCheckCycleLimitReco()

        # Case A: max_cycles=3
        my_reco.mobile_ad_state["completed_cycles"] = 2
        res = reco.analyze(None, _FakeArg(json.dumps({"max_cycles": 3})))
        self.assertIsNone(res)

        my_reco.mobile_ad_state["completed_cycles"] = 3
        res = reco.analyze(None, _FakeArg(json.dumps({"max_cycles": 3})))
        self.assertEqual(res, (0, 0, 10, 10))

        # Case B: max_cycles=0
        my_reco.mobile_ad_state["completed_cycles"] = 0
        res = reco.analyze(None, _FakeArg(json.dumps({"max_cycles": 0})))
        self.assertIsNone(res)

        my_reco.mobile_ad_state["completed_cycles"] = 100
        res = reco.analyze(None, _FakeArg(json.dumps({"max_cycles": 0})))
        self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()
