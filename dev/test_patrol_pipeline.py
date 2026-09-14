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
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
    "[JumpBack]PatrolShellEntryMisTouchPopup",
    "[JumpBack]PatrolShellPagePopup",
}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


def load_image(path):
    with open(path, "rb") as f:
        return cv2.imdecode(np.frombuffer(f.read(), dtype=np.uint8), cv2.IMREAD_UNCHANGED)


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
        mis_touch_template_path = os.path.join(
            ROOT, "assets", "resource", "image", "开贝壳_误触识别.png"
        )
        self.assertTrue(
            os.path.isfile(mis_touch_template_path),
            "开贝壳_误触识别.png 模板文件必须存在",
        )

        patrol_entry = self.pipeline["PatrolShellEntryMisTouchPopup"]
        self.assertEqual(patrol_entry["recognition"], "TemplateMatch")
        self.assertEqual(patrol_entry["template"], "开贝壳_误触识别.png")
        self.assertEqual(patrol_entry["roi"], [498, 80, 280, 191])
        self.assertEqual(patrol_entry["action"], "DoNothing")
        self.assertNotIn("target", patrol_entry)
        self.assertEqual(
            business_next(patrol_entry), ["PatrolShellEntryMisTouchReturn"]
        )

        patrol_entry_return = self.pipeline["PatrolShellEntryMisTouchReturn"]
        self.assertEqual(patrol_entry_return["recognition"], "OCR")
        self.assertEqual(patrol_entry_return["expected"], "返回")
        self.assertEqual(patrol_entry_return["roi"], [1, 0, 189, 119])
        self.assertEqual(patrol_entry_return["action"], "Click")
        self.assertNotIn("target", patrol_entry_return)

        for node_name, node in self.pipeline.items():
            successors = node.get("next", [])
            if "[JumpBack]PatrolShellPagePopup" not in successors:
                continue
            self.assertIn(
                "[JumpBack]PatrolShellEntryMisTouchPopup",
                successors,
                node_name,
            )
            self.assertLess(
                successors.index("[JumpBack]PatrolShellEntryMisTouchPopup"),
                successors.index("[JumpBack]PatrolShellPagePopup"),
                node_name,
            )

        # 1-8. Verify 开贝壳_识别.png template and ROI [37, 68, 226, 142] across all 3 usage sites
        shell_template_path = os.path.join(ROOT, "assets", "resource", "image", "开贝壳_识别.png")
        self.assertTrue(os.path.isfile(shell_template_path), "开贝壳_识别.png 模板文件必须存在")

        handler = self.pipeline["PatrolShellPagePopup"]
        self.assertEqual(handler["recognition"], "TemplateMatch")
        self.assertEqual(handler["template"], "开贝壳_识别.png")
        self.assertEqual(handler["roi"], [37, 68, 226, 142])
        self.assertEqual(handler["action"], "DoNothing")
        self.assertNotIn("target", handler)
        self.assertEqual(business_next(handler), ["PatrolShellPageReturn"])

        # 9. 贝壳页面_返回.png 仍然只能在页面本体门禁之后点击
        return_node = self.pipeline["PatrolShellPageReturn"]
        self.assertEqual(return_node["recognition"], "TemplateMatch")
        self.assertEqual(return_node["template"], "贝壳页面_返回.png")
        self.assertEqual(return_node["roi"], [0, 0, 250, 150])
        self.assertEqual(return_node["action"], "Click")
        self.assertNotIn("target", return_node)

        # OpenShellTask entry routing (supports deep resume at start page or entry from main tank)
        self.assertEqual(
            business_next(self.open_shell_pipeline["OpenShellTask"]),
            ["OpenShellStartPage", "OpenShellEntry", "OpenShellAbort"],
        )

        entry = self.open_shell_pipeline["OpenShellEntry"]
        self.assertEqual(entry["recognition"], "TemplateMatch")
        self.assertEqual(entry["template"], "开贝壳_入口.png")
        self.assertEqual(entry["roi"], [289, 492, 168, 139])
        self.assertEqual(entry["action"], "Click")
        self.assertNotIn("target", entry)
        # 1. OpenShellEntry 的业务 next 不再直接是 OpenShellStartPage
        self.assertNotIn("OpenShellStartPage", business_next(entry))
        # 2. OpenShellEntry -> OpenShellEnter
        self.assertEqual(business_next(entry), ["OpenShellEnter"])
        self.assertEqual(entry.get("on_error"), ["OpenShellAbort"])
        self.assertTrue(
            os.path.isfile(
                os.path.join(ROOT, "assets", "resource", "image", "开贝壳_入口.png")
            )
        )

        # 3. OpenShellEnter: OCR, expected "^进入$", roi [271, 573, 101, 45], action Click
        enter_node = self.open_shell_pipeline["OpenShellEnter"]
        self.assertEqual(enter_node["recognition"], "OCR")
        self.assertEqual(enter_node["expected"], "^进入$")
        self.assertEqual(enter_node["roi"], [271, 573, 101, 45])
        self.assertEqual(enter_node["action"], "Click")
        self.assertNotIn("target", enter_node)
        self.assertEqual(enter_node.get("on_error"), ["OpenShellAbort"])
        # 4. OpenShellEnter -> OpenShellStartPage
        self.assertEqual(business_next(enter_node), ["OpenShellStartPage"])

        # 5. OpenShellStartPage ROI == [37, 68, 226, 142]
        start_page = self.open_shell_pipeline["OpenShellStartPage"]
        self.assertEqual(start_page["recognition"], "TemplateMatch")
        self.assertEqual(start_page["template"], "开贝壳_识别.png")
        self.assertEqual(start_page["roi"], [37, 68, 226, 142])
        self.assertEqual(start_page["action"], "DoNothing")
        self.assertEqual(business_next(start_page), ["OpenShellRoundStart"])

        # 6. CollectFish.HandleShellPage ROI == [37, 68, 226, 142]
        collect_handler = self.collect_fish_pipeline["HandleShellPage"]
        self.assertEqual(collect_handler["template"], "开贝壳_识别.png")
        self.assertEqual(collect_handler["roi"], [37, 68, 226, 142])
        self.assertEqual(collect_handler["action"], "DoNothing")
        self.assertEqual(business_next(collect_handler), ["HandleShellPageReturn"])

        collect_return = self.collect_fish_pipeline["HandleShellPageReturn"]
        self.assertEqual(collect_return["template"], "贝壳页面_返回.png")
        self.assertEqual(collect_return["roi"], [0, 0, 250, 150])
        self.assertEqual(collect_return["action"], "Click")
        self.assertEqual(business_next(collect_return), ["ResumeHarvest"])

        collect_entry = self.collect_fish_pipeline["HandleShellEntryMisTouch"]
        self.assertEqual(collect_entry["template"], "开贝壳_误触识别.png")
        self.assertEqual(collect_entry["roi"], [498, 80, 280, 191])
        self.assertEqual(collect_entry["action"], "DoNothing")
        self.assertEqual(
            business_next(collect_entry), ["HandleShellEntryMisTouchReturn"]
        )
        collect_entry_return = self.collect_fish_pipeline[
            "HandleShellEntryMisTouchReturn"
        ]
        self.assertEqual(collect_entry_return["recognition"], "OCR")
        self.assertEqual(collect_entry_return["expected"], "返回")
        self.assertEqual(collect_entry_return["roi"], [1, 0, 189, 119])
        self.assertEqual(collect_entry_return["action"], "Click")
        self.assertNotIn("target", collect_entry_return)
        self.assertEqual(business_next(collect_entry_return), ["ResumeHarvest"])

        for router_name in ("ResumeHarvest", "CheckDutyCycle"):
            route = business_next(self.collect_fish_pipeline[router_name])
            self.assertLess(
                route.index("HandleShellEntryMisTouch"),
                route.index("HandleShellPage"),
            )

        # 10. 原 OpenShell 后半段拓扑保持不变
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellRoundStart"]), ["OpenShellOpenFirst"])
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellOpenFirst"]), ["OpenShellResultRouter"])
        self.assertEqual(
            business_next(self.open_shell_pipeline["OpenShellResultRouter"]),
            ["OpenShellOctopus", "OpenShellFinish", "OpenShellContinue"],
        )
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellContinue"]), ["OpenShellResultRouter"])
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellOctopus"]), ["OpenShellFinish"])
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellFinish"]), ["OpenShellConfirmReturn"])
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellConfirmReturn"]), ["OpenShellLoopRouter"])
        self.assertEqual(
            business_next(self.open_shell_pipeline["OpenShellLoopRouter"]),
            ["OpenShellShouldContinue", "OpenShellDone"],
        )
        self.assertEqual(business_next(self.open_shell_pipeline["OpenShellShouldContinue"]), ["OpenShellRoundStart"])

        done = self.open_shell_pipeline["OpenShellDone"]
        self.assertEqual(done["recognition"], "OCR")
        self.assertEqual(done["expected"], "返回")
        self.assertEqual(done["roi"], [0, 0, 173, 123])
        self.assertEqual(done["action"], "Click")
        self.assertNotIn("target", done)
        self.assertEqual(business_next(done), ["OpenShellVerifyMainAfterDone"])

        verify_main = self.open_shell_pipeline["OpenShellVerifyMainAfterDone"]
        self.assertEqual(verify_main["template"], "主界面特征.png")
        self.assertEqual(verify_main["roi"], [0, 200, 150, 400])
        self.assertEqual(verify_main["action"], "DoNothing")
        self.assertEqual(verify_main["on_error"], ["OpenShellAbort"])

        for tank in (1, 2, 3):
            sweep = self.pipeline[f"PatrolSweepTank{tank}AfterBubble"]
            self.assertIn("[JumpBack]PatrolShellEntryMisTouchPopup", sweep["next"])
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
            image_window = self.pipeline[f"PatrolCollectTank{tank}ImageWindow"]
            bubble = self.pipeline[f"PatrolCollectTank{tank}Bubble"]
            self.assertEqual(window["recognition"], "DirectHit")
            self.assertEqual(window["timeout"], 30000)
            self.assertIn(f"PatrolCollectTank{tank}Bubble", window["next"])
            expected_next = (
                f"PatrolPreSwitchCheckTank{tank}"
                if tank < 3
                else "PatrolPreManagementCheckTank3"
            )
            self.assertEqual(window["on_error"], [expected_next])
            self.assertEqual(image_window["recognition"], "DirectHit")
            self.assertEqual(image_window["timeout"], 30000)
            self.assertIn(f"PatrolCollectTank{tank}Bubble", image_window["next"])
            self.assertEqual(image_window["on_error"], [expected_next])
            self.assertEqual(bubble["roi"], [0, 100, 1280, 560])
            sweep_name = f"PatrolSweepTank{tank}AfterBubble"
            self.assertEqual(business_next(bubble), [sweep_name])
            self.assertEqual(
                business_next(self.pipeline[sweep_name]),
                [f"PatrolCollectTank{tank}ImageWindow"],
            )

    def test_shake_mode_falls_back_to_image_recognition_before_switching_tanks(self):
        for tank in (1, 2, 3):
            shake = self.pipeline[f"PatrolCollectTank{tank}ShakeGem"]
            self.assertEqual(
                business_next(shake),
                [f"PatrolCollectTank{tank}ImageWindow"],
            )
            focus = " ".join(shake.get("focus", {}).values())
            self.assertIn("图像识别", focus)
            self.assertIn("30 秒", focus)

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
            self.assertEqual(special["roi"], [450, 151, 199, 191])
            self.assertEqual(special["target"], [649, 204, 57, 91])
            self.assertLessEqual(
                special["roi"][0] + special["roi"][2],
                special["target"][0],
                f"{key} 的鱼食点击区不得与加号门禁重叠",
            )

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
        self.assertIn("[JumpBack]GlobalNewsPopup", next_nodes)
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
            "PatrolGemFusionPutInStorage": ("宝石融合_产物识别.png", [172, 128, 230, 212]),
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
        product = self.pipeline["PatrolGemFusionPutInStorage"]
        self.assertEqual(product["action"], "DoNothing")
        self.assertEqual(business_next(product), ["PatrolGemFusionConfirmPutInStorage"])

        store = self.pipeline["PatrolGemFusionConfirmPutInStorage"]
        self.assertEqual(store["recognition"], "OCR")
        self.assertEqual(store["expected"], "放入仓库")
        self.assertEqual(store["roi"], [565, 537, 152, 42])
        self.assertEqual(store["action"], "Click")
        self.assertNotIn("target", store)
        self.assertEqual(business_next(store), ["PatrolGemFusionVerifyPage"])
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
            "PatrolGemFusionPutInStorage": ("上一轮", "产物"),
            "PatrolGemFusionConfirmPutInStorage": ("放入仓库", "本轮合成"),
            "PatrolGemFusionClickSynthesize": ("已启动", "宝石融合"),
        }.items():
            focus = " ".join(self.pipeline[node_name].get("focus", {}).values())
            for fragment in fragments:
                self.assertIn(fragment, focus, node_name)

    def test_gem_fusion_return_router_prioritizes_put_in_storage_and_fallbacks(self):
        first_return = self.pipeline["PatrolGemFusionReturn"]
        self.assertEqual(business_next(first_return), ["PatrolGemFusionReturnRouter"])
        self.assertIn("第一次返回", " ".join(first_return["focus"].values()))

        router = self.pipeline["PatrolGemFusionReturnRouter"]
        router_next = business_next(router)

        # Case 1: 第一次返回后若已回鱼缸，MainTank 优先级高于后续页面处理，不进入 PutInStorage
        main_tanks = [
            "PatrolVerifyMainTank1AfterCycle",
            "PatrolVerifyMainTank2AfterCycle",
            "PatrolVerifyMainTank3AfterCycle",
        ]
        self.assertEqual(router_next[:3], main_tanks)
        for tank in main_tanks:
            self.assertLess(router_next.index(tank), router_next.index("PatrolGemFusionConfirmPutInStorage"))

        # Case 2 & Case 3: 未回鱼缸时，优先检测【放入仓库】，位于 StillOnPage 之前
        self.assertEqual(
            router_next[3:],
            [
                "PatrolGemFusionConfirmPutInStorage",
                "PatrolGemFusionStillOnPage",
                "PatrolGemFusionAbort",
            ],
        )
        self.assertLess(
            router_next.index("PatrolGemFusionConfirmPutInStorage"),
            router_next.index("PatrolGemFusionStillOnPage"),
        )

        # Case 4: 领取奖励后复用现有融合链 (ConfirmPutInStorage -> VerifyPage -> Synthesize/Running -> Return)
        confirm_store = self.pipeline["PatrolGemFusionConfirmPutInStorage"]
        self.assertEqual(confirm_store["recognition"], "OCR")
        self.assertEqual(confirm_store["expected"], "放入仓库")
        self.assertEqual(confirm_store["roi"], [565, 537, 152, 42])
        self.assertEqual(confirm_store["action"], "Click")
        self.assertEqual(business_next(confirm_store), ["PatrolGemFusionVerifyPage"])

        verify_page = self.pipeline["PatrolGemFusionVerifyPage"]
        verify_next = business_next(verify_page)
        self.assertIn("PatrolGemFusionClickSynthesize", verify_next)
        self.assertIn("PatrolGemFusionAlreadyRunning", verify_next)
        self.assertEqual(business_next(self.pipeline["PatrolGemFusionClickSynthesize"]), ["PatrolGemFusionReturn"])
        self.assertEqual(business_next(self.pipeline["PatrolGemFusionAlreadyRunning"]), ["PatrolGemFusionReturn"])

        # 防死循环断言：PutInStorage 链路中确认入库后必须推进到 VerifyPage，不直接循环回 ReturnRouter
        self.assertNotIn("PatrolGemFusionReturnRouter", business_next(confirm_store))

        # Case 5: 无奖励但仍在融合页时，走 StillOnPage -> ReturnAgain -> MainTank Verify
        still_page = self.pipeline["PatrolGemFusionStillOnPage"]
        self.assertEqual(still_page["recognition"], "TemplateMatch")
        self.assertEqual(still_page["template"], "宝石融合页面.png")
        self.assertEqual(still_page["roi"], [549, 0, 178, 242])
        self.assertEqual(still_page["action"], "DoNothing")
        self.assertEqual(business_next(still_page), ["PatrolGemFusionReturnAgain"])

        retry = self.pipeline["PatrolGemFusionReturnAgain"]
        self.assertEqual(retry["recognition"], "OCR")
        self.assertEqual(retry["expected"], "返回")
        self.assertEqual(retry["action"], "Click")
        self.assertEqual(business_next(retry), ["PatrolVerifyMainAfterCycle"])

        # Case 6: 未知状态安全熔断 (Abort)
        self.assertEqual(router_next[-1], "PatrolGemFusionAbort")
        self.assertEqual(self.pipeline["PatrolGemFusionAbort"]["action"], "StopTask")

        # Case 7: 魔力召唤业务链保持完好且未被修改
        magic_due = self.pipeline["PatrolMagicSummonDue"]
        self.assertIn("PatrolMagicOpenTreasure", business_next(magic_due))
        magic_router = self.pipeline["PatrolMagicVerifyPage"]
        self.assertEqual(
            business_next(magic_router),
            [
                "PatrolMagicConfirmPopup",
                "PatrolMagicRevealResult",
                "PatrolMagicClickAdvanced",
                "PatrolMagicAlreadyRunning",
            ],
        )

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
        self.assertEqual(task["option"], ["多鱼缸巡检间隔", "多鱼缸巡检子任务", "收宝石方式"])
        option = payloads[0]["option"]["多鱼缸巡检间隔"]
        self.assertEqual(option["default_case"], "30分钟")
        extras = payloads[0]["option"]["多鱼缸巡检子任务"]
        self.assertEqual(extras["default_case"], [])
        self.assertEqual(
            [case["name"] for case in extras["cases"]],
            ["魔力召唤", "宝石融合"],
        )

    def test_starfish_mis_touch_recovery_topology_for_all_tanks(self):
        """Case 1, Case 2, Case 3: Verify mis-touch recovery chain for Tank 1, 2, 3."""
        for tank in (1, 2, 3):
            mis_touch = self.pipeline[f"PatrolStarfishPetPanelMisTouchTank{tank}"]
            ret_node = self.pipeline[f"PatrolStarfishPetPanelReturnTank{tank}"]
            verify_node = self.pipeline[f"PatrolVerifyTank{tank}AfterStarfishMisTouch"]

            # Recognition & gating
            self.assertEqual(mis_touch["recognition"], "OCR")
            self.assertEqual(mis_touch["expected"], "[萌乖亮]海星")
            self.assertEqual(mis_touch["roi"], [80, 70, 800, 100])
            self.assertEqual(mis_touch["action"], "DoNothing")
            self.assertEqual(business_next(mis_touch), [f"PatrolStarfishPetPanelReturnTank{tank}"])

            # Return click
            self.assertEqual(ret_node["recognition"], "OCR")
            self.assertEqual(ret_node["expected"], "返回")
            self.assertEqual(ret_node["roi"], [1, 0, 189, 119])
            self.assertEqual(ret_node["action"], "Click")
            self.assertEqual(business_next(ret_node), [f"PatrolVerifyTank{tank}AfterStarfishMisTouch"])

            # Verify tank identity
            self.assertEqual(verify_node["recognition"], "TemplateMatch")
            self.assertEqual(verify_node["template"], f"patrol/鱼缸{tank}_主页面编号.png")
            self.assertEqual(verify_node["threshold"], 0.85)
            self.assertEqual(verify_node["roi"], [40, 32, 45, 48])
            self.assertEqual(verify_node["action"], "DoNothing")

            # Returns to ImageWindow to restart 30s observation
            self.assertEqual(business_next(verify_node), [f"PatrolCollectTank{tank}ImageWindow"])
            self.assertEqual(self.pipeline[f"PatrolCollectTank{tank}ImageWindow"]["timeout"], 30000)

    def test_starfish_mis_touch_priority_over_bubble_and_timeout(self):
        """Case 4: In PatrolCollectTankXImageWindow.next and PatrolCollectTankX.next, mis-touch precedes bubble."""
        for tank in (1, 2, 3):
            for node_name in (f"PatrolCollectTank{tank}", f"PatrolCollectTank{tank}ImageWindow"):
                next_nodes = self.pipeline[node_name]["next"]
                mis_touch_idx = next_nodes.index(f"PatrolStarfishPetPanelMisTouchTank{tank}")
                bubble_idx = next_nodes.index(f"PatrolCollectTank{tank}Bubble")
                self.assertLess(mis_touch_idx, bubble_idx, f"{node_name} must prioritize mis-touch over bubble")

    def test_starfish_mis_touch_does_not_falsely_match_generic_page(self):
        """Case 5: Mis-touch recognition requires unique starfish tab pattern [萌乖亮]海星, not bare 返回."""
        for tank in (1, 2, 3):
            mis_touch = self.pipeline[f"PatrolStarfishPetPanelMisTouchTank{tank}"]
            self.assertNotEqual(mis_touch["expected"], "返回")
            self.assertIn("海星", mis_touch["expected"])
            self.assertIn(mis_touch["roi"][1], range(50, 120))

    def test_normal_patrol_starfish_feeding_isolated_from_mis_touch(self):
        """Case 6: Normal starfish feeding business pipeline does not route through mis-touch recovery nodes."""
        normal_chain = [
            "PatrolOpenManagement",
            "PatrolVerifyManagement",
            "PatrolOpenUniversalStarfish",
            "PatrolSelectCuteStarfishTab",
            "PatrolCuteFeedCheck",
            "PatrolSelectGoodStarfishTab",
            "PatrolGoodFeedCheck",
            "PatrolSelectBrightStarfishTab",
            "PatrolBrightFeedCheck",
            "PatrolExitUniversalStarfish",
            "PatrolVerifyManagementAfterStarfish",
            "PatrolExitManagement",
        ]
        mis_touch_names = {
            f"PatrolStarfishPetPanelMisTouchTank{i}" for i in (1, 2, 3)
        } | {
            f"PatrolStarfishPetPanelReturnTank{i}" for i in (1, 2, 3)
        }
        for node_name in normal_chain:
            if node_name in self.pipeline:
                node = self.pipeline[node_name]
                for nxt in node.get("next", []):
                    self.assertNotIn(nxt, mis_touch_names, f"{node_name} must not route to mis-touch nodes")
        for name in mis_touch_names:
            self.assertNotIn(name, GLOBAL_HANDLERS)

    def test_pre_switch_state_protection_and_abort_fallback(self):
        """Case 7: Before opening picker or management, verify tank page; recovery or abort if not main tank."""
        for tank in (1, 2):
            pre_switch = self.pipeline[f"PatrolPreSwitchCheckTank{tank}"]
            self.assertEqual(pre_switch["recognition"], "DirectHit")
            next_nodes = business_next(pre_switch)
            self.assertEqual(
                next_nodes,
                [
                    f"PatrolStarfishPetPanelMisTouchTank{tank}",
                    f"PatrolOpenPickerAfterTank{tank}",
                    "PatrolAbortNavigation",
                ],
            )
            picker_node = self.pipeline[f"PatrolOpenPickerAfterTank{tank}"]
            self.assertEqual(picker_node["recognition"], "TemplateMatch")
            self.assertEqual(picker_node["template"], f"patrol/鱼缸{tank}_主页面编号.png")
            self.assertEqual(picker_node["threshold"], 0.85)

        pre_mgmt = self.pipeline["PatrolPreManagementCheckTank3"]
        self.assertEqual(pre_mgmt["recognition"], "DirectHit")
        self.assertEqual(
            business_next(pre_mgmt),
            [
                "PatrolStarfishPetPanelMisTouchTank3",
                "PatrolOpenManagement",
                "PatrolAbortNavigation",
            ],
        )

    def test_no_error_handling_loops_in_patrol_collect(self):
        """Case 8: Ensure no on_error loops (e.g. ImageWindow -> on_error -> ImageWindow)."""
        for tank in (1, 2, 3):
            image_window = self.pipeline[f"PatrolCollectTank{tank}ImageWindow"]
            self.assertNotIn(f"PatrolCollectTank{tank}ImageWindow", image_window.get("on_error", []))
            for err_target in image_window.get("on_error", []):
                target_node = self.pipeline.get(err_target, {})
                self.assertNotIn(f"PatrolCollectTank{tank}ImageWindow", target_node.get("on_error", []))


if __name__ == "__main__":
    unittest.main()

