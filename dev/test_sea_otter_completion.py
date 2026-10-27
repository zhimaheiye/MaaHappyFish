"""Real endpoint frames and native mode/count routing; no emulator access."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action as actions, local_state
from agent.my_reco import CheckSeaOtterNormalCompletionReco
from agent.runtime_state import sea_otter_gem_state
from maa.controller import CustomController
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


@pytest.mark.parametrize("endpoint", ["last_friend_exhausted", "recommended"])
@pytest.mark.parametrize("mode", ["manual", "auto", "return_failed"])
def test_native_confirmed_scan_endpoint_counts_once(endpoint, mode):
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/sea-otter-completion-native"))

    def read(path):
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        assert frame is not None
        return frame

    endpoint_frame = read(ROOT / f"dev/fixtures/sea_otter/completion_20261027/{endpoint}.png")
    main = read(ROOT / "dev/fixtures/fish_baby/live_20260923/15_returned_main_tank.png")

    class Controller(CustomController):
        frame = endpoint_frame
        clicks = []
        def connect(self): return True
        def request_uuid(self): return "offline-sea-otter-completion"
        def get_features(self): return 0
        def screencap(self): return self.frame
        def click(self, x, y):
            self.clicks.append((x, y))
            # A successful auto return switches to a real main-tank frame.
            self.frame = main if mode == "auto" else np.zeros((720, 1280, 3), np.uint8)
            return True

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    for name in ("SeaOtterBoundaryIncompleteAction", "SeaOtterReturnFromRecommendedAction",
                 "SeaOtterFinalizeAction", "SeaOtterHomeReturnClickAction",
                 "SeaOtterHomeReturnWaitAction", "FailTaskAction"):
        assert resource.register_custom_action(name, getattr(actions, name)())
    assert resource.register_custom_recognition("CheckSeaOtterNormalCompletionReco", CheckSeaOtterNormalCompletionReco())
    overrides = {name: {"enabled": False} for name in resource.node_list if name.startswith("Global")}
    overrides["SeaOtterHomeClickBack"] = {"post_delay": 0}
    overrides["SeaOtterHomeReturnWait"] = {"post_delay": 0}
    if mode == "manual":
        interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
        manual = interface["option"]["海獭摸宝运行模式"]["cases"][1]
        overrides.update(manual["pipeline_override"])
    assert resource.override_pipeline(overrides)
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    saved = copy.deepcopy(sea_otter_gem_state)
    try:
        sea_otter_gem_state.update(current_side="left", normal_completion=False, completion_reason=None,
                                   daily_count_recorded=False, home_return_ticks=0, home_return_waits=0)
        entry = "SeaOtterGrayRightArrow" if endpoint == "last_friend_exhausted" else "SeaOtterRecommendedBridge"
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MAAHAPPYFISH_STATE_DIR": tmp}), \
             patch.object(local_state, "write_sea_otter_status_markdown"), \
             patch.object(actions, "_HOME_RETURN_WAIT_LIMIT", 1):
            result = tasker.post_task(entry).wait()
            assert result.succeeded == (mode != "return_failed")
            assert sea_otter_gem_state["normal_completion"]
            assert local_state.get_sea_otter_daily_count() == (0 if mode == "return_failed" else 1)
            assert len(controller.clicks) == (0 if mode == "manual" else 1)
            assert all(0 <= x < 189 and 0 <= y < 146 for x, y in controller.clicks)
            if mode != "return_failed":
                ctx = SimpleNamespace(tasker=SimpleNamespace(running=True, stopping=False), override_pipeline=lambda _: True)
                assert actions.SeaOtterFinalizeAction().run(ctx, SimpleNamespace(custom_action_param="null"))
                assert local_state.get_sea_otter_daily_count() == 1
    finally:
        sea_otter_gem_state.clear()
        sea_otter_gem_state.update(saved)


def test_stop_after_endpoint_does_not_record_completion():
    with patch.dict(sea_otter_gem_state, {"normal_completion": True, "daily_count_recorded": False}), \
         patch.object(local_state, "record_sea_otter_completed_run") as record:
        ctx = SimpleNamespace(tasker=SimpleNamespace(running=True, stopping=True))
        assert not actions.SeaOtterFinalizeAction().run(ctx, SimpleNamespace())
        record.assert_not_called()
