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
            "EmulatorAdClosePage": ("看广告页面_关闭.png", "Click"),
            "EmulatorAdStopEnabled": ("停止按钮_可点击.png", "Click"),
            "EmulatorAdStopDisabled": ("停止按钮_不可点击.png", "DoNothing"),
            "EmulatorAdRewardPopup": ("下一段视频_对号.png", "Custom"),
            "EmulatorAdContinue": ("下一段视频_对号.png", "Click"),
            "EmulatorAdCloseRewardAndDone": ("看广告页面_关闭.png", "Click"),
        }
        for node_name, (template, action) in expected_templates.items():
            node = self.pipeline[node_name]
            self.assertEqual(node["recognition"], "TemplateMatch")
            self.assertEqual(node["template"], template)
            self.assertEqual(node["roi"], [0, 0, 1280, 720])
            self.assertEqual(node["threshold"], 0.8)
            self.assertEqual(node["action"], action)
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
        self.assertEqual(self.pipeline["EmulatorAdClosePage"]["next"], ["EmulatorAdPostAdRouter"])
        self.assertEqual(self.pipeline["EmulatorAdStopEnabled"]["next"], ["EmulatorAdPostStopRouter"])
        self.assertEqual(self.pipeline["EmulatorAdStopDisabled"]["next"], ["EmulatorAdPostStopRouter"])
        for node_name in ("EmulatorAdPostAdRouter", "EmulatorAdPostStopRouter"):
            self.assertEqual(
                self.pipeline[node_name]["next"],
                ["EmulatorAdRewardPopup", "EmulatorAdStopEnabled", "EmulatorAdStopDisabled"],
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
        self.assertEqual(task["option"], ["手机广告轮数"])

        option = self.interface["option"]["手机广告轮数"]
        expected_cycles = {"3 轮(默认测试)": 3, "5 轮": 5, "10 轮": 10}
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

    def test_external_ad_pipeline_is_isolated_from_game_popup_handlers(self):
        source = (ROOT / "dev" / "test_daily_sign_global.py").read_text(encoding="utf-8")
        self.assertIn('"emulator_ads.json"', source)


if __name__ == "__main__":
    unittest.main()
