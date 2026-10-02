"""真实 MaaFramework 文件帧回放；不连接模拟器，所有点击/滑动仅记录。"""
import json
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker

Library.open(Library.framework_libpath.parent, agent_server=False)
FIXTURES = ROOT / "dev/fixtures/patrol/accidental_activity_20261002"
MAIN = ROOT / "dev/fixtures/patrol/image/main"


def image(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


class FileController(CustomController):
    def __init__(self, frame, after_click=None):
        self.frame = frame
        self.after_click = after_click
        self.clicks = []
        self.swipes = []
        super().__init__()

    def connect(self):
        return True

    def request_uuid(self):
        return "offline-patrol-activity"

    def get_features(self):
        return 0

    def screencap(self):
        return self.frame.copy()

    def click(self, x, y):
        self.clicks.append((x, y))
        if self.after_click is not None:
            self.frame = self.after_click.copy()
        return True

    def swipe(self, x1, y1, x2, y2, duration):
        self.swipes.append((x1, y1, x2, y2))
        return True


class ActivityMisTouch(unittest.TestCase):
    def setup_tasker(self, frame, after_click=None):
        resource = Resource()
        self.assertTrue(resource.post_bundle(ROOT / "assets/resource").wait().succeeded)
        resource.register_custom_action("ClickRecognizedCenterAction", my_action.ClickRecognizedCenterAction())
        resource.register_custom_action("FailTaskAction", my_action.FailTaskAction())
        controller = FileController(frame, after_click)
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        return tasker, resource, controller

    def test_saved_activities_cannot_click_coins_or_sweep_even_with_a_coin_hit(self):
        tasker, resource, controller = self.setup_tasker(image(FIXTURES / "harvest_board.png"))
        checks = []

        class Probe(CustomAction):
            def run(self, context, argv):
                for path in sorted(FIXTURES.glob("*.png")):
                    frame = image(path)
                    for tank in (1, 2, 3):
                        for node in (f"PatrolCollectTank{tank}Bubble", f"PatrolSweepTank{tank}AfterBubble", f"PatrolSweepTank{tank}BackAfterBubble"):
                            hit = context.run_recognition(node, frame)
                            if hit is None or hit.hit:
                                return False
                            checks.append((path.name, node))
                return True

        resource.register_custom_action("OfflineProbe", Probe())
        self.assertTrue(tasker.post_task("OfflineProbe", {
            "OfflineProbe": {"recognition": "DirectHit", "action": "Custom", "custom_action": "OfflineProbe"},
            # 故意把气泡识别强制为真，证明拒绝来自正向页面门禁。
            "PatrolCoinIdentity": {"recognition": "DirectHit"},
        }).wait().succeeded)
        self.assertEqual(len(checks), 45)
        self.assertEqual(controller.clicks, [])
        self.assertEqual(controller.swipes, [])

    def test_coin_box_and_click_center_stay_inside_existing_safe_roi(self):
        tasker, resource, controller = self.setup_tasker(image(MAIN / "tank2_main.png"))
        boxes = []

        class Probe(CustomAction):
            def run(self, context, argv):
                frame = controller.frame
                hit = context.run_recognition("PatrolCollectTank2Bubble", frame)
                if hit is None or not hit.hit:
                    return False
                boxes.append(tuple(hit.box))
                # 帧中真实金币不能让另外两个缸的识别门禁通过。
                return all(not context.run_recognition(f"PatrolCollectTank{tank}Bubble", frame).hit for tank in (1, 3))

        resource.register_custom_action("OfflineProbe", Probe())
        self.assertTrue(tasker.post_task("OfflineProbe", {"OfflineProbe": {
            "recognition": "DirectHit", "action": "Custom", "custom_action": "OfflineProbe"
        }}).wait().succeeded)
        x, y, w, h = boxes[0]
        self.assertGreaterEqual(x, 428)
        self.assertGreaterEqual(y, 126)
        self.assertLessEqual(x + w, 1107)
        self.assertLessEqual(y + h, 486)
        self.assertTrue(tasker.post_task("PatrolCollectTank2Bubble", {
            "PatrolCollectTank2Bubble": {"next": [], "post_delay": 0}
        }).wait().succeeded)
        self.assertEqual(controller.clicks, [(x + w // 2, y + h // 2)])

    def test_page_change_after_coin_click_blocks_both_swipes_and_reports_failure(self):
        tasker, resource, controller = self.setup_tasker(
            image(MAIN / "tank2_main.png"), image(FIXTURES / "harvest_board.png"))
        result = tasker.post_task("PatrolCollectTank2Bubble", {
            "PatrolCollectTank2Bubble": {"timeout": 100, "on_error": ["PatrolAbortNavigation"]},
            "PatrolSweepTank2AfterBubble": {"timeout": 100},
            "PatrolCollectTank2ImageWindow": {"timeout": 100, "next": ["PatrolCollectTank2Bubble"]},
        }).wait()
        self.assertTrue(result.failed)
        self.assertEqual(len(controller.clicks), 1)
        self.assertEqual(controller.swipes, [])

    def test_unchanged_tank_still_runs_forward_and_reverse_sweeps(self):
        tasker, resource, controller = self.setup_tasker(image(MAIN / "tank2_main.png"))
        result = tasker.post_task("PatrolCollectTank2Bubble", {
            "PatrolSweepTank2BackAfterBubble": {"next": []}
        }).wait()
        self.assertTrue(result.succeeded)
        self.assertEqual(len(controller.clicks), 1)
        self.assertEqual(controller.swipes, [(221, 663, 1007, 663), (1007, 663, 221, 663)])

    def test_abort_returns_native_failed_instead_of_green_success(self):
        tasker, resource, controller = self.setup_tasker(image(FIXTURES / "harvest_board.png"))
        for name in ("PatrolAbortNavigation", "PatrolAbortUnknownPage"):
            self.assertTrue(tasker.post_task(name).wait().failed)
        self.assertEqual(controller.clicks, [])
        self.assertEqual(controller.swipes, [])


if __name__ == "__main__":
    unittest.main()
