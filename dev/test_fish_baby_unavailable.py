"""Native file-frame replay for an unavailable incubation button; no device."""
import copy
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.my_action import DailyRoutineSubtaskDoneAction, FailTaskAction
from agent.my_reco import FishBabyHomePageReco, CheckDailyRoutineActiveReco
from agent.runtime_state import daily_routine_state
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


@pytest.mark.parametrize("mode", ["daily", "standalone", "exit_stuck", "unknown", "category"])
def test_unavailable_start_closes_home_and_only_skips_after_tank(mode):
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/fish-baby-unavailable-native"))
    fixtures = ROOT / "dev/fixtures/fish_baby"

    def read(path):
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        assert frame is not None
        return frame

    frames = {"home": read(fixtures / "start_unavailable_20261027.png"),
              "tank": read(fixtures / "live_20260923/15_returned_main_tank.png"),
              "category": read(fixtures / "live_20260923/01_incubation_categories.png"),
              "unknown": np.zeros((720, 1280, 3), np.uint8)}
    clicks = []
    continued = []

    class Controller(CustomController):
        page = "home"
        def connect(self): return True
        def request_uuid(self): return "offline-fish-baby-unavailable"
        def get_features(self): return 0
        def screencap(self): return frames[self.page]
        def click(self, x, y):
            clicks.append((x, y))
            if 1200 <= x <= 1225 and 55 <= y <= 82:
                if mode != "exit_stuck": self.page = "tank"
            elif mode in ("unknown", "category"):
                self.page = mode
            return True

    class Continue(CustomAction):
        def run(self, context, argv):
            continued.append(daily_routine_state["step"])
            return True

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    for name, action in (("DailyRoutineSubtaskDoneAction", DailyRoutineSubtaskDoneAction()),
                         ("FailTaskAction", FailTaskAction()), ("OfflineContinue", Continue())):
        assert resource.register_custom_action(name, action)
    assert resource.register_custom_recognition("FishBabyHomePageReco", FishBabyHomePageReco())
    assert resource.register_custom_recognition("CheckDailyRoutineActiveReco", CheckDailyRoutineActiveReco())
    assert resource.override_pipeline({
        **{name: {"enabled": False} for name in resource.node_list if name.startswith("Global")},
        # Only shorten waits and replace the following business stage; real page gates stay active.
        "FishBabyHomeStart": {"post_delay": 0, "timeout": 0},
        "FishBabyUnavailableExitHome": {"post_delay": 0, "timeout": 0},
        "FishBabyUnavailableVerifyTank": {"timeout": 0},
        "FishBabyRunRound": {"action": "Custom", "custom_action": "OfflineContinue", "next": []},
        "DailyRoutineReturnIfActive": {"next": ["OfflineContinue"]},
        "OfflineContinue": {"recognition": "DirectHit", "action": "Custom", "custom_action": "OfflineContinue"},
    })
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    saved = copy.deepcopy(daily_routine_state)
    try:
        daily_routine_state.update(active=mode != "standalone", step="FISH_BABY",
                                   queue=["PRINCESS_TASK"], tasks={"FishBaby": {"status": "IDLE"}})
        result = tasker.post_task("FishBabyHomeStart").wait()
        assert result.succeeded == (mode in ("daily", "standalone", "category"))
        assert 510 <= clicks[0][0] <= 770 and 600 <= clicks[0][1] <= 710
        assert len(clicks) == (1 if mode in ("unknown", "category") else 2)
        if len(clicks) == 2:
            assert 1200 <= clicks[1][0] <= 1225 and 55 <= clicks[1][1] <= 82
        if mode == "daily":
            assert daily_routine_state["tasks"]["FishBaby"]["status"] == "SKIPPED"
            assert daily_routine_state["step"] == "PRINCESS_TASK"
            assert continued == ["PRINCESS_TASK"]
        else:
            assert daily_routine_state["tasks"]["FishBaby"]["status"] == "IDLE"
            assert daily_routine_state["step"] == "FISH_BABY"
            assert continued == (["FISH_BABY"] if mode == "category" else [])
    finally:
        daily_routine_state.clear()
        daily_routine_state.update(saved)


def test_only_home_start_failure_can_use_skip_exit():
    nodes = json.loads((ROOT / "assets/resource/pipeline/features/fish_baby.json").read_text(encoding="utf-8"))
    assert nodes["FishBabyHomeStart"]["on_error"] == ["FishBabyIncubationCategory", "FishBabyUnavailableExitHome", "FishBabyAbort"]
    skip = nodes["FishBabyUnavailableExitHome"]
    assert skip["all_of"] == nodes["FishBabyExitHome"]["all_of"]
    assert skip["target"] == nodes["FishBabyExitHome"]["target"]
    assert skip["next"][-1] == "FishBabyUnavailableVerifyTank"
    verify = nodes["FishBabyUnavailableVerifyTank"]
    assert verify["template"] == "主界面特征.png"
    assert verify["custom_action_param"]["status"] == "SKIPPED"
    assert verify["on_error"] == ["FishBabyAbort"]
    assert nodes["FishBabyRunRound"]["on_error"] == ["FishBabyAbort"]
