"""Delayed friend-tab navigation and safe patrol recovery; no device access."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action as actions


@pytest.mark.parametrize("scenario, expected, count", [
    ("delayed", True, 1), ("retry", True, 2), ("stuck", False, 2),
    ("unknown", False, 1), ("already", True, 0),
    ("stop", False, 1), ("capture_failed", False, 1), ("click_failed", False, 1),
])
def test_tab_wait_rechecks_before_retry(scenario, expected, count):
    clock = [0.0]
    clicks = []
    tasker = SimpleNamespace(stopping=False, running=True)

    def sleep(seconds):
        clock[0] += seconds
        if scenario == "stop":
            tasker.stopping = True

    def page():
        if scenario == "already": return "list"
        if scenario == "delayed" and clock[0] >= 3.5: return "list"
        if scenario == "retry" and len(clicks) >= 2 and clock[0] >= 9: return "list"
        if scenario == "unknown" and clicks: return "unknown"
        return "inbox"

    def capture(ctrl):
        if scenario == "capture_failed" and clicks: return None
        return page()

    def recognize(ctx, name, frame):
        if name == "FriendPageStarFriendsIdentity" and frame == "list": return (131, 114, 145, 28)
        if name == "FriendGemMessageInbox" and frame == "inbox": return (76, 118, 453, 31)
        return None

    def click(x, y):
        clicks.append((x, y, clock[0]))
        return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=scenario != "click_failed"))

    controller = SimpleNamespace(post_click=click)
    tasker.controller = controller
    context = SimpleNamespace(tasker=tasker)
    with patch.object(actions, "_capture_720p", side_effect=capture), \
         patch.object(actions, "_recognition_box", side_effect=recognize), \
         patch.object(actions.time, "monotonic", side_effect=lambda: clock[0]), \
         patch.object(actions.time, "sleep", side_effect=sleep):
        assert actions._open_star_friends(context, controller) is expected
    assert len(clicks) == count
    assert all((x, y) == (493, 45) for x, y, _ in clicks)
    if count == 2:
        assert clicks[1][2] - clicks[0][2] >= 8


def test_native_real_frames_gate_patrol_return_and_failure_status():
    import cv2
    from maa.controller import CustomController
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/friend-tab-native"))
    fixture = ROOT / "dev/fixtures/friend_gem/tab_delay_20261027"
    current = [None]

    class Controller(CustomController):
        def connect(self): return True
        def request_uuid(self): return "offline-friend-tab"
        def get_features(self): return 0
        def screencap(self): return current[0]

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    resource.register_custom_action("FailTaskAction", actions.FailTaskAction())
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    # Preserve all real recognition gates; disable actions and successors.
    for filename, expected in (("star_friends.png", True), ("inbox.png", False)):
        current[0] = cv2.imdecode(np.frombuffer((fixture / filename).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        for node in ("FriendPageStarFriendsIdentity", "PatrolStartAtFriendList"):
            result = tasker.post_task(node, {node: {"action": "DoNothing", "next": [],
                                                    "on_error": [], "timeout": 0, "focus": {}}}).wait()
            assert result.succeeded is expected, (filename, node)
    assert tasker.post_task("FriendPageNavigationFailed").wait().failed


def test_patrol_return_has_verified_target_and_bounded_main_tank_wait():
    pipeline = json.loads((ROOT / "assets/resource/pipeline/features/patrol.json").read_text(encoding="utf-8"))
    node = pipeline["PatrolStartAtFriendList"]
    assert "PatrolStartAtFriendList" in pipeline["PatrolStartRouter"]["next"]
    assert node["all_of"][0] == "FriendPageStarFriendsIdentity"
    assert node["all_of"][1] == {"recognition": "OCR", "expected": "^返回$", "roi": [1, 0, 189, 119]}
    assert node["box_index"] == 1
    assert node["custom_action"] == "ClickRecognizedCenterAction"
    assert "target" not in node
    assert node["next"][5:] == ["PatrolStartAtTank1", "PatrolStartAtTank2", "PatrolStartAtTank3"]
    assert node["timeout"] == 8000
    assert node["on_error"] == ["PatrolAbortNavigation"]
