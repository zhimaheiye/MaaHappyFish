"""Offline native replay: a missing claim entrance must not restart shell/buy."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.my_action import (FailTaskAction, InitGreenWildDailyAction,
                             GreenWildDailyDoneAction, GreenWildClaimDoneAction)
from agent.my_reco import CheckDailyRoutineStepReco, CheckDailyRoutineActiveReco
from agent.runtime_state import daily_routine_state, green_wild_daily_state
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


@pytest.mark.parametrize("mode", ["standalone", "nested", "success"])
def test_native_missing_claim_entrance_does_not_repeat_consumption(mode):
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/green-wild-native"))
    saved = copy.deepcopy(daily_routine_state)
    saved_green = copy.deepcopy(green_wild_daily_state)
    visits = []

    class Controller(CustomController):
        def connect(self): return True
        def request_uuid(self): return "offline-green-wild-failure"
        def get_features(self): return 0
        def screencap(self): return np.zeros((720, 1280, 3), dtype=np.uint8)

    class Record(CustomAction):
        def run(self, context, argv):
            visits.append(json.loads(argv.custom_action_param))
            # A regression must end the replay promptly, never hang the test.
            return len(visits) <= 3

    class Nested(CustomAction):
        def run(self, context, argv):
            result = context.clone().run_task("DailyRoutineDispatcher")
            return result is not None and result.status.succeeded

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    for name, action in (("FailTaskAction", FailTaskAction()),
                         ("InitGreenWildDailyAction", InitGreenWildDailyAction()),
                         ("GreenWildDailyDoneAction", GreenWildDailyDoneAction()),
                         ("GreenWildClaimDoneAction", GreenWildClaimDoneAction()),
                         ("OfflineRecord", Record()), ("OfflineNested", Nested())):
        assert resource.register_custom_action(name, action)
    assert resource.register_custom_recognition("CheckDailyRoutineStepReco", CheckDailyRoutineStepReco())
    assert resource.register_custom_recognition("CheckDailyRoutineActiveReco", CheckDailyRoutineActiveReco())
    overrides = {name: {"enabled": False} for name in resource.node_list
                 if name.startswith("Global") or name.startswith("DailyRoutineStep")}
    overrides.update({
        "DailyRoutineStepGreenWildDaily": {"enabled": True},
        "DailyRoutineStepPrincessTask": {"enabled": True, "action": "Custom",
                                         "custom_action": "OfflineRecord", "custom_action_param": "next",
                                         "next": []},
        # Replay the observed successful shell, buy and return stages without clicks.
        "OpenShellStartRouter": {"recognition": "DirectHit", "action": "Custom",
                                 "custom_action": "OfflineRecord", "custom_action_param": "shell",
                                 "next": ["OfflineBuy"]},
        "OfflineBuy": {"recognition": "DirectHit", "action": "Custom",
                       "custom_action": "OfflineRecord", "custom_action_param": "buy",
                       "next": ["GreenWildDailyVerifyTank"]},
        "GreenWildDailyVerifyTank": {"recognition": "DirectHit", "post_delay": 0},
        # Keep the real StartRouter and Abort links; simulate all visual candidates missing.
        **{name: {"enabled": False} for name in
           ("GreenWildClaimAll", "GreenWildOpenTask", "GreenWildOpenTaskByOcr", "GreenWildEntry")},
        "GreenWildStartRouter": {"post_delay": 0},
        "OfflineOuter": {"recognition": "DirectHit", "action": "Custom", "custom_action": "OfflineNested"},
    })
    if mode == "success":
        overrides["GreenWildStartRouter"]["next"] = ["GreenWildVerifyTank"]
        overrides["GreenWildVerifyTank"] = {"recognition": "DirectHit"}
    assert resource.override_pipeline(overrides)
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    try:
        daily_routine_state.update(active=True, step="GREEN_WILD_DAILY", queue=["PRINCESS_TASK"],
                                   tasks={"GreenWildDaily": {"status": "IDLE"}})
        result = tasker.post_task("OfflineOuter" if mode == "nested" else "DailyRoutineDispatcher").wait()
        assert result.succeeded == (mode == "success")
        assert visits == (["shell", "buy", "next"] if mode == "success" else ["shell", "buy"])
        assert not green_wild_daily_state["pending_buy_fish"]
        if mode == "success":
            assert daily_routine_state["step"] == "PRINCESS_TASK"
            assert daily_routine_state["tasks"]["GreenWildDaily"]["status"] == "DONE"
        else:
            assert daily_routine_state["step"] == "GREEN_WILD_DAILY"
            assert daily_routine_state["queue"] == ["PRINCESS_TASK"]
            assert daily_routine_state["tasks"]["GreenWildDaily"]["status"] == "IDLE"
    finally:
        daily_routine_state.clear()
        daily_routine_state.update(saved)
        green_wild_daily_state.clear()
        green_wild_daily_state.update(saved_green)
