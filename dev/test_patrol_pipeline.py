import json
import os
import unittest

import cv2
import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_PATH = os.path.join(
    ROOT, "assets", "resource", "pipeline", "features", "patrol.json"
)
EXTRAS_PIPELINE_PATH = os.path.join(
    ROOT, "assets", "resource", "pipeline", "features", "patrol_extras.json"
)
OPEN_SHELL_PIPELINE_PATH = os.path.join(
    ROOT, "assets", "resource", "pipeline", "features", "open_shell.json"
)
COLLECT_FISH_PIPELINE_PATH = os.path.join(
    ROOT, "assets", "resource", "pipeline", "collect_fish.json"
)
INTERFACE_PATHS = [
    os.path.join(ROOT, "assets", "interface.json"),
    os.path.join(ROOT, "client", "interface.json"),
    os.path.join(ROOT, "client_avalonia", "interface.json"),
]
FIXTURE_ROOT = os.path.join(ROOT, "dev", "fixtures", "patrol", "image")
GLOBAL_HANDLERS = {
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]PatrolShellPagePopup",
}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


def load_image(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)


def template_score(screen, template, roi):
    x, y, width, height = roi
    crop = screen[y : y + height, x : x + width]
    if template.shape[2] == 4:
        result = cv2.matchTemplate(
            crop[:, :, :3],
            template[:, :, :3],
            cv2.TM_CCORR_NORMED,
            mask=template[:, :, 3],
        )
    else:
        result = cv2.matchTemplate(crop[:, :, :3], template[:, :, :3], cv2.TM_CCOEFF_NORMED)
    return cv2.minMaxLoc(result)[1]


class PatrolPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PIPELINE_PATH, "r", encoding="utf-8") as file:
            cls.pipeline = json.load(file)
        with open(EXTRAS_PIPELINE_PATH, "r", encoding="utf-8") as file:
            cls.pipeline.update(json.load(file))
        with open(OPEN_SHELL_PIPELINE_PATH, "r", encoding="utf-8") as file:
            cls.open_shell_pipeline = json.load(file)
        with open(COLLECT_FISH_PIPELINE_PATH, "r", encoding="utf-8") as file:
            cls.collect_fish_pipeline = json.load(file)

    def test_clicks_are_guarded_by_visual_recognition(self):
        explicit_user_targets = {
            "PatrolCuteSpecialFood",
            "PatrolGoodSpecialFood",
            "PatrolBrightSpecialFood",
        }
        for name, node in self.pipeline.items():
            if node.get("action") == "Click":
                self.assertIn(node.get("recognition"), {"OCR", "TemplateMatch"}, name)
                if name not in explicit_user_targets:
                    self.assertNotIn("target", node, name)

    def test_open_shell_page_is_verified_before_clicking_return(self):
        handler = self.pipeline["PatrolShellPagePopup"]
        self.assertEqual(handler["recognition"], "TemplateMatch")
        self.assertEqual(handler["template"], "开贝壳_识别.png")
        self.assertEqual(handler["roi"], [508, 70, 263, 201])
        self.assertEqual(handler["action"], "DoNothing")
        self.assertNotIn("target", handler)
        self.assertEqual(business_next(handler), ["PatrolShellPageReturn"])

        return_node = self.pipeline["PatrolShellPageReturn"]
        self.assertEqual(return_node["recognition"], "TemplateMatch")
        self.assertEqual(return_node["template"], "贝壳页面_返回.png")
        self.assertEqual(return_node["roi"], [0, 0, 250, 150])
        self.assertEqual(return_node["action"], "Click")
        self.assertNotIn("target", return_node)

        start_page = self.open_shell_pipeline["OpenShellStartPage"]
        self.assertEqual(start_page["recognition"], "TemplateMatch")
        self.assertEqual(start_page["template"], "开贝壳_识别.png")
        self.assertEqual(start_page["roi"], [508, 70, 263, 201])
        self.assertEqual(start_page["action"], "DoNothing")
        self.assertEqual(business_next(start_page), ["OpenShellRoundStart"])
        self.assertEqual(
            business_next(self.open_shell_pipeline["OpenShellTask"]),
            ["OpenShellStartPage"],
        )

        collect_handler = self.collect_fish_pipeline["HandleShellPage"]
        self.assertEqual(collect_handler["template"], "开贝壳_识别.png")
        self.assertEqual(collect_handler["roi"], [508, 70, 263, 201])
        self.assertEqual(collect_handler["action"], "DoNothing")
        self.assertEqual(business_next(collect_handler), ["HandleShellPageReturn"])

        collect_return = self.collect_fish_pipeline["HandleShellPageReturn"]
        self.assertEqual(collect_return["template"], "贝壳页面_返回.png")
        self.assertEqual(collect_return["roi"], [0, 0, 250, 150])
        self.assertEqual(collect_return["action"], "Click")
        self.assertEqual(business_next(collect_return), ["ResumeHarvest"])

        for tank in (1, 2, 3):
            sweep = self.pipeline[f"PatrolSweepTank{tank}AfterBubble"]
            self.assertIn("[JumpBack]PatrolShellPagePopup", sweep["next"])

    def test_start_router_supports_known_resume_stages(self):
        next_nodes = self.pipeline["PatrolStartRouter"]["next"]
        for node in (
            "PatrolStartAtFoodPopupAbort",
            "PatrolStartAtUniversalStarfish",
            "PatrolStartAtManagement",
            "PatrolStartAtPicker",
            "PatrolStartAtTank1",
            "PatrolStartAtTank2",
            "PatrolStartAtTank3",
        ):
            self.assertIn(node, next_nodes)

    def test_each_tank_uses_a_30_second_inactivity_window(self):
        for tank in (1, 2, 3):
            window = self.pipeline[f"PatrolCollectTank{tank}"]
            bubble = self.pipeline[f"PatrolCollectTank{tank}Bubble"]
            self.assertEqual(window["recognition"], "DirectHit")
            self.assertEqual(window["timeout"], 30000)
            self.assertIn(f"PatrolCollectTank{tank}Bubble", window["next"])
            expected_next = (
                f"PatrolOpenPickerAfterTank{tank}"
                if tank < 3
                else "PatrolOpenManagement"
            )
            self.assertEqual(window["on_error"], [expected_next])
            self.assertEqual(bubble["roi"], [0, 100, 1280, 560])
            sweep_name = f"PatrolSweepTank{tank}AfterBubble"
            self.assertEqual(business_next(bubble), [sweep_name])
            self.assertEqual(
                business_next(self.pipeline[sweep_name]),
                [f"PatrolCollectTank{tank}"],
            )

    def test_main_patrol_steps_report_actions_and_results(self):
        expected_logs = {
            "PatrolStartAtTank1": ("鱼缸 1", "检查产物"),
            "PatrolVerifyTank1Main": ("鱼缸 1", "检查产物"),
            "PatrolOpenPickerAfterTank1": ("鱼缸 1", "30 秒", "鱼缸 2"),
            "PatrolVerifyTank2Main": ("鱼缸 2", "检查产物"),
            "PatrolOpenPickerAfterTank2": ("鱼缸 2", "30 秒", "鱼缸 3"),
            "PatrolVerifyTank3Main": ("鱼缸 3", "检查产物"),
            "PatrolOpenManagement": ("鱼缸 3", "30 秒", "管理页"),
            "PatrolVerifyManagement": ("管理页", "确认"),
            "PatrolExitManagement": ("返回", "主鱼缸"),
        }
        for node_name, fragments in expected_logs.items():
            focus = " ".join(self.pipeline[node_name].get("focus", {}).values())
            for fragment in fragments:
                self.assertIn(fragment, focus, node_name)

        for tank in (1, 2, 3):
            self.assertNotIn(
                "focus",
                self.pipeline[f"PatrolSweepTank{tank}AfterBubble"],
            )

        for key, label in (
            ("Cute", "萌海星"),
            ("Good", "乖海星"),
            ("Bright", "亮海星"),
        ):
            expected = {
                f"PatrolSelect{key}StarfishTab": (label, "切换"),
                f"PatrolVerify{key}Starfish": (label, "确认"),
                f"Patrol{key}Replenish": (label, "选择鱼食"),
                f"Patrol{key}NormalFood": (label, "普通鱼食", "投放"),
                f"Patrol{key}SpecialFood": (label, "专用鱼食", "投放"),
                f"Patrol{key}FeedReturnedToPanel": (label, "投放成功"),
            }
            for node_name, fragments in expected.items():
                focus = " ".join(self.pipeline[node_name].get("focus", {}).values())
                for fragment in fragments:
                    self.assertIn(fragment, focus, node_name)

    def test_starfish_page_is_entered_once_then_switched_by_tabs(self):
        self.assertEqual(
            business_next(self.pipeline["PatrolVerifyManagement"]),
            ["PatrolOpenUniversalStarfish"],
        )
        entry = self.pipeline["PatrolOpenUniversalStarfish"]
        self.assertEqual(entry["recognition"], "OCR")
        self.assertEqual(entry["expected"], "海星")
        self.assertEqual(entry["action"], "Click")

        for key, label in (
            ("Cute", "萌海星"),
            ("Good", "乖海星"),
            ("Bright", "亮海星"),
        ):
            tab = self.pipeline[f"PatrolSelect{key}StarfishTab"]
            self.assertEqual(tab["recognition"], "OCR")
            self.assertEqual(tab["expected"], label)
            self.assertEqual(tab["roi"], [80, 70, 800, 100])
            self.assertEqual(tab["action"], "Click")
            verify = self.pipeline[f"PatrolVerify{key}Starfish"]
            self.assertEqual(verify["expected"], label)
            self.assertEqual(verify["roi"], [330, 140, 420, 130])

        old_management_nodes = {
            f"PatrolManagementSelectTank{tank}" for tank in (1, 2, 3)
        }
        self.assertTrue(old_management_nodes.isdisjoint(self.pipeline))

    def test_each_starfish_chooses_food_from_the_actual_popup(self):
        for key in ("Cute", "Good", "Bright"):
            router = self.pipeline[f"Patrol{key}FoodRouter"]
            self.assertEqual(router["recognition"], "DirectHit")
            self.assertEqual(
                business_next(router)[:2],
                [f"Patrol{key}NormalFood", f"Patrol{key}SpecialFood"],
            )

            normal = self.pipeline[f"Patrol{key}NormalFood"]
            self.assertEqual(normal["template"], "普通鱼食袋.png")
            self.assertNotIn("target", normal)

            special = self.pipeline[f"Patrol{key}SpecialFood"]
            self.assertEqual(special["template"], "海星_加号.png")
            self.assertEqual(special["roi"], [457, 216, 189, 186])
            self.assertEqual(special["target"], [579, 210, 196, 195])

            after = self.pipeline[f"Patrol{key}AfterFeedRouter"]
            self.assertEqual(after["recognition"], "DirectHit")
            self.assertEqual(business_next(after)[0], "PatrolFoodPopupStillOpen")

        popup = self.pipeline["PatrolFoodPopupStillOpen"]
        self.assertEqual(popup["recognition"], "OCR")
        self.assertEqual(popup["expected"], "选择喂食")
        self.assertEqual(popup["action"], "StopTask")

    def test_tank_switches_have_post_click_verification(self):
        self.assertEqual(
            business_next(self.pipeline["PatrolSelectTank2FromPicker"]),
            ["PatrolVerifyTank2Main"],
        )
        self.assertEqual(
            business_next(self.pipeline["PatrolSelectTank3FromPicker"]),
            ["PatrolVerifyTank3Main"],
        )
    def test_main_tank_templates_match_recorded_main_frames(self):
        for tank in (1, 2, 3):
            node = self.pipeline[f"PatrolVerifyTank{tank}Main"]
            self.assertNotEqual(node["template"], f"patrol/鱼缸{tank}_入口.png")
            template = load_image(
                os.path.join(ROOT, "assets", "resource", "image", node["template"])
            )
            self.assertIsNotNone(template)
            for frame_tank in (1, 2, 3):
                frame = load_image(
                    os.path.join(FIXTURE_ROOT, "main", f"tank{frame_tank}_main.png")
                )
                self.assertIsNotNone(frame)
                score = template_score(frame, template, node["roi"])
                if frame_tank == tank:
                    self.assertGreaterEqual(
                        score,
                        node["threshold"],
                        f"tank {tank} main template does not match its real main-page frame",
                    )
                else:
                    self.assertLess(
                        score,
                        node["threshold"],
                        f"tank {tank} main template falsely matches tank {frame_tank}",
                    )

    def test_picker_targets_use_separate_real_button_regions(self):
        frame = load_image(os.path.join(FIXTURE_ROOT, "picker", "tank_picker.png"))
        rois = []
        for tank in (1, 2, 3):
            node = self.pipeline[f"PatrolSelectTank{tank}FromPicker"]
            rois.append(node["roi"])
            template = load_image(
                os.path.join(ROOT, "assets", "resource", "image", node["template"])
            )
            self.assertGreaterEqual(
                template_score(frame, template, node["roi"]),
                node["threshold"],
                f"tank {tank} picker template does not match its own button region",
            )
        self.assertEqual(len({tuple(roi) for roi in rois}), 3)

    def test_wait_loop_keeps_global_popups_active(self):
        next_nodes = self.pipeline["PatrolWaitLoop"]["next"]
        self.assertIn("[JumpBack]GlobalDailySignPopup", next_nodes)
        self.assertIn("[JumpBack]GlobalSpecialOfferPopup", next_nodes)
        self.assertIn("PatrolTimerDue", next_nodes)
        self.assertEqual(
            self.pipeline["PatrolTimerDue"]["custom_recognition"],
            "CheckPatrolTimerReco",
        )

    def test_wait_loop_priority_is_main_then_magic_then_fusion(self):
        next_nodes = self.pipeline["PatrolWaitLoop"]["next"]
        self.assertLess(next_nodes.index("PatrolTimerDue"), next_nodes.index("PatrolMagicSummonDue"))
        self.assertLess(next_nodes.index("PatrolMagicSummonDue"), next_nodes.index("PatrolGemFusionDue"))
        for node_name, feature in (
            ("PatrolMagicSummonDue", "magic_summon"),
            ("PatrolGemFusionDue", "gem_fusion"),
        ):
            node = self.pipeline[node_name]
            self.assertFalse(node["enabled"])
            self.assertEqual(node["custom_recognition"], "CheckPatrolFeatureTimerReco")
            self.assertEqual(node["custom_recognition_param"]["feature"], feature)
            self.assertEqual(node["custom_recognition_param"]["interval"], 3600)

    def test_optional_feature_rois_follow_user_supplied_evidence(self):
        expected = {
            "PatrolMagicOpenTreasure": ("右下角_宝箱.png", [1120, 562, 141, 141]),
            "PatrolMagicClickEntry": ("魔力召唤入口.png", [415, 593, 173, 124]),
            "PatrolMagicClickAdvanced": ("点击高级召唤.png", [811, 495, 232, 148]),
            "PatrolMagicConfirmPopup": ("绿色勾选按钮.png", [751, 404, 153, 150]),
            "PatrolGemFusionOpenTreasure": ("右下角_宝箱.png", [1120, 562, 141, 141]),
            "PatrolGemFusionClickEntry": ("宝石融合入口.png", [632, 591, 135, 128]),
            "PatrolGemFusionVerifyPage": ("宝石融合页面.png", [549, 0, 178, 242]),
        }
        for node_name, (template, roi) in expected.items():
            node = self.pipeline[node_name]
            self.assertEqual(node["template"], template)
            self.assertEqual(node["roi"], roi)
            self.assertTrue(
                os.path.isfile(
                    os.path.join(ROOT, "assets", "resource", "image", template)
                ),
                template,
            )
        self.assertEqual(
            self.pipeline["PatrolGemFusionPutInStorage"]["roi"],
            [498, 486, 283, 138],
        )
        self.assertEqual(
            self.pipeline["PatrolGemFusionClickSynthesize"]["roi"],
            [825, 556, 178, 140],
        )
        self.assertEqual(
            self.pipeline["PatrolMagicRevealResult"]["roi"],
            [827, 501, 210, 145],
        )
        self.assertEqual(
            self.pipeline["PatrolMagicConfirmRevealedResult"]["roi"],
            [538, 399, 202, 142],
        )
        magic_expected = self.pipeline["PatrolMagicVerifyPage"]["expected"]
        self.assertIn("魔力", magic_expected)
        self.assertIn("召唤", magic_expected)

    def test_magic_summon_routes_completed_result_back_to_start_flow(self):
        router_next = business_next(self.pipeline["PatrolMagicVerifyPage"])
        self.assertEqual(
            router_next,
            [
                "PatrolMagicConfirmPopup",
                "PatrolMagicRevealResult",
                "PatrolMagicClickAdvanced",
                "PatrolMagicAlreadyRunning",
            ],
        )
        reveal = self.pipeline["PatrolMagicRevealResult"]
        self.assertEqual(reveal["recognition"], "OCR")
        self.assertEqual(reveal["expected"], "揭晓")
        self.assertEqual(reveal["action"], "Click")
        self.assertEqual(
            business_next(reveal),
            ["PatrolMagicConfirmRevealedResult"],
        )
        confirm = self.pipeline["PatrolMagicConfirmRevealedResult"]
        self.assertEqual(confirm["recognition"], "OCR")
        self.assertEqual(confirm["expected"], "确定")
        self.assertEqual(confirm["action"], "Click")
        self.assertEqual(business_next(confirm), ["PatrolMagicClickAdvanced"])

    def test_optional_features_report_each_terminal_state(self):
        magic = self.pipeline["PatrolMagicAlreadyRunning"]
        self.assertEqual(magic["action"], "DoNothing")
        self.assertEqual(business_next(magic), ["PatrolMagicReturn"])
        magic_focus = " ".join(magic["focus"].values())
        self.assertIn("正在召唤", magic_focus)
        self.assertIn("未重复", magic_focus)

        fusion = self.pipeline["PatrolGemFusionAlreadyRunning"]
        self.assertEqual(fusion["action"], "DoNothing")
        self.assertEqual(business_next(fusion), ["PatrolGemFusionReturn"])
        fusion_focus = " ".join(fusion["focus"].values())
        self.assertIn("正在融合", fusion_focus)
        self.assertIn("未重复", fusion_focus)

        for node_name, fragments in {
            "PatrolMagicRevealResult": ("上一轮", "揭晓"),
            "PatrolMagicConfirmPopup": ("已启动", "魔力召唤"),
            "PatrolGemFusionPutInStorage": ("上一轮", "放入仓库"),
            "PatrolGemFusionClickSynthesize": ("已启动", "宝石融合"),
        }.items():
            focus = " ".join(self.pipeline[node_name].get("focus", {}).values())
            for fragment in fragments:
                self.assertIn(fragment, focus, node_name)

    def test_management_resume_accepts_any_main_tank_on_exit(self):
        next_nodes = self.pipeline["PatrolVerifyMainAfterCycle"]["next"]
        for tank in (1, 2, 3):
            self.assertIn(f"PatrolVerifyMainTank{tank}AfterCycle", next_nodes)
            self.assertEqual(
                business_next(self.pipeline[f"PatrolVerifyMainTank{tank}AfterCycle"]),
                ["PatrolWaitLoop"],
            )

    def test_interfaces_are_synced_and_expose_patrol(self):
        payloads = []
        raw_files = []
        for path in INTERFACE_PATHS:
            with open(path, "rb") as file:
                raw_files.append(file.read())
            payloads.append(json.loads(raw_files[-1].decode("utf-8-sig")))
        self.assertEqual(raw_files[0], raw_files[1])
        self.assertEqual(raw_files[0], raw_files[2])
        task = next(item for item in payloads[0]["task"] if item["entry"] == "PatrolTask")
        self.assertEqual(task["option"], ["多鱼缸巡检间隔", "多鱼缸巡检子任务"])
        option = payloads[0]["option"]["多鱼缸巡检间隔"]
        self.assertEqual(option["default_case"], "30分钟")
        extras = payloads[0]["option"]["多鱼缸巡检子任务"]
        self.assertEqual(extras["default_case"], [])
        self.assertEqual(
            [case["name"] for case in extras["cases"]],
            ["魔力召唤", "宝石融合"],
        )


if __name__ == "__main__":
    unittest.main()
