"""2026-10-03 海獭边界回归：固定现场帧/真实 MaaFramework，不连接设备。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action, local_state
from agent.my_reco import CheckSeaOtterLimitReco
from agent.runtime_state import sea_otter_gem_state
from maa.controller import CustomController
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
import cv2
import numpy as np

Library.open(Library.framework_libpath.parent, agent_server=False)


class SavedFrameController(CustomController):
    def __init__(self):
        path = ROOT / "dev/fixtures/desktop_reports_20261003/sea_otter/last_friend_exhausted.png"
        self.frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.clicks = []
        super().__init__()

    def connect(self):
        return self.frame is not None

    def request_uuid(self):
        return "offline-sea-otter-boundary"

    def get_features(self):
        return 0

    def screencap(self):
        return self.frame.copy()

    def click(self, x, y):
        self.clicks.append((x, y))
        return True


class BoundaryRecovery(unittest.TestCase):
    def test_native_endpoint_and_safety_are_failed_without_count_or_click(self):
        resource = Resource()
        self.assertTrue(resource.post_bundle(ROOT / "assets/resource").wait().succeeded)
        for name in ("SeaOtterBoundaryIncompleteAction", "SeaOtterFinalizeAction",
                     "SeaOtterReturnFromRecommendedAction", "FailTaskAction",
                     "SeaOtterHomeReturnClickAction", "SeaOtterHomeReturnWaitAction"):
            resource.register_custom_action(name, getattr(my_action, name)())
        resource.register_custom_recognition("CheckSeaOtterLimitReco", CheckSeaOtterLimitReco())
        controller = SavedFrameController()
        self.assertTrue(controller.post_connection().wait().succeeded)
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        pipeline = json.loads((ROOT / "assets/resource/pipeline/features/sea_otter_gem.json").read_text(encoding="utf-8"))
        # 本例只测海獭业务分支；已有全局弹窗由全量接入门禁检查。
        override = {name: {**node, "next": [n for n in node["next"] if not n.startswith("[JumpBack]")]}
                    for name, node in pipeline.items() if node.get("next")}
        cases = [
            ("SeaOtterGrayRightArrow", {}, {}),  # 真实末位帧 OCR 0(12点刷新体力)。
            ("SeaOtterAddFriendPage", {}, {"recognition": "DirectHit"}),
            ("SeaOtterRecommendedBridge", {}, {"recognition": "DirectHit"}),
            ("SeaOtterLimitReached", {"total_harvests": 1000}, {}),
            ("SeaOtterLimitReached", {"consecutive_exhausted": 30}, {}),
            ("SeaOtterNavigationFailed", {}, {}),
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MAAHAPPYFISH_STATE_DIR": tmp}):
            state = Path(tmp) / "state.json"
            self.assertEqual(local_state.record_sea_otter_completed_run(), (1, 3))
            saved = state.read_bytes()
            for entry, changes, recognition in cases:
                with self.subTest(entry=entry, changes=changes), patch.dict(sea_otter_gem_state, {
                        "current_side": "left", "total_harvests": 0, "max_harvests": 1000,
                        "consecutive_exhausted": 0, "max_consecutive_exhausted": 30,
                        "normal_completion": False, "completion_reason": None,
                        "daily_count_recorded": False, "home_return_ticks": 0,
                        "home_return_waits": 0, **changes}, clear=True):
                    controller.clicks.clear()
                    nodes = {name: dict(node) for name, node in override.items()}
                    if recognition:
                        nodes[entry] = {**nodes.get(entry, pipeline[entry]), **recognition}
                    self.assertTrue(tasker.post_task(entry, nodes).wait().failed)
                    self.assertFalse(sea_otter_gem_state["normal_completion"])
                    self.assertEqual(state.read_bytes(), saved)
                    if entry == "SeaOtterGrayRightArrow":
                        self.assertLessEqual(len(controller.clicks), 6)
                        for x, y in controller.clicks:
                            self.assertLess(x, 189)
                            self.assertLess(y, 146)
                    else:
                        self.assertEqual(controller.clicks, [])

    def test_right_exhausted_bridge_rejects_unknown_frame_and_failed_prev(self):
        for mode in ("empty", "missing_gate", "prev_unchanged", "stop"):
            with self.subTest(mode=mode), patch.dict(sea_otter_gem_state, {
                    "current_side": "right", "normal_completion": False,
                    "completion_reason": None}, clear=True):
                clicks = []
                ctrl = SimpleNamespace(post_click=lambda x, y: (
                    clicks.append((x, y)) or SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=True))))
                ctx = SimpleNamespace(
                    tasker=SimpleNamespace(controller=ctrl, running=True, stopping=(mode == "stop")),
                    run_recognition=lambda name, frame: SimpleNamespace(
                        hit=(mode != "missing_gate"), box=(120, 220, 290, 50)))
                argv = SimpleNamespace(custom_action_param={"reason": "LAST_FRIEND_STAMINA_UNVERIFIED"})
                with patch.object(my_action, "_capture_720p", return_value=None if mode == "empty" else 0), \
                     patch.object(my_action.time, "sleep"):
                    self.assertFalse(my_action.SeaOtterBoundaryIncompleteAction().run(ctx, argv))
                self.assertEqual(clicks, [(1085, 68)] if mode == "prev_unchanged" else [])
                self.assertFalse(sea_otter_gem_state["normal_completion"])


if __name__ == "__main__":
    unittest.main()
