"""Replay the 2026-10-28 ready-button failure with native OCR, never a device."""
import copy
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from my_reco import CheckFishingCastLimitReco, CheckFishingDailyReselectOrdinaryReco
from my_action import FishingCastAndBiteQTEAction
from runtime_state import fishing_state
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


def test_ready_regex_preserves_button_scope():
    nodes = json.loads((ROOT / "assets/resource/pipeline/features/fishing.json").read_text(encoding="utf-8"))
    for name in ("FishingRound", "FishingPostRoundCheckReady"):
        node = nodes[name]
        assert node["roi"] == [1050, 520, 160, 100]
        for text in ("甩杆", "甩桿"):
            assert re.fullmatch(node["expected"], text)
        for text in ("收杆", "收桿", "查看鱼", "购买鱼饵"):
            assert not re.search(node["expected"], text)


def test_action_still_refuses_sixth_cast():
    saved = copy.deepcopy(fishing_state)
    try:
        fishing_state.update(cast_count=5, max_casts=5)
        # No controller exists: reaching touch dispatch would fail this test.
        assert FishingCastAndBiteQTEAction().run(
            SimpleNamespace(), SimpleNamespace(custom_action_param="null", task_detail=None)
        ) is False
        assert fishing_state["cast_count"] == 5
    finally:
        fishing_state.clear()
        fishing_state.update(saved)


@pytest.mark.parametrize("casts,unknown", [(1, False), (5, False), (1, True)])
def test_native_post_round_recovers_ready_or_preserves_limit(casts, unknown):
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/fishing-ready-ocr-native"))
    path = ROOT / "dev/fixtures/fishing/ready_20261028.png"
    frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None
    if unknown:
        frame = np.zeros_like(frame)
    reached = []

    class Controller(CustomController):
        def connect(self): return True
        def request_uuid(self): return "offline-fishing-ready-ocr"
        def get_features(self): return 0
        def screencap(self): return frame
        def click(self, x, y):
            raise AssertionError("Offline replay must never click or consume bait")

    class Record(CustomAction):
        def run(self, context, argv):
            reached.append(argv.node_name)
            return True

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    assert resource.register_custom_action("OfflineFishingRecord", Record())
    assert resource.register_custom_recognition("CheckFishingCastLimitReco", CheckFishingCastLimitReco())
    assert resource.register_custom_recognition("CheckFishingDailyReselectOrdinaryReco", CheckFishingDailyReselectOrdinaryReco())
    assert resource.override_pipeline({
        **{name: {"enabled": False} for name in resource.node_list if name.startswith("Global")},
        # Keep both real OCR gates and real loop/limit routing. Replace only
        # consuming actions and subsequent exit stages with recording leaves.
        "FishingRound": {"action": "Custom", "custom_action": "OfflineFishingRecord", "next": [], "on_error": []},
        "FishingDone": {"action": "Custom", "custom_action": "OfflineFishingRecord", "next": [], "on_error": []},
        "FishingPostRoundRouter": {"timeout": 0},
        "FishingPostRoundWait": {"enabled": False},
    })
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    saved = copy.deepcopy(fishing_state)
    try:
        fishing_state.update(cast_count=casts, max_casts=5, force_ordinary_bait=False)
        result = tasker.post_task("FishingPostRoundRouter").wait()
        assert result.succeeded == (not unknown)
        assert reached == ([] if unknown else ["FishingDone" if casts == 5 else "FishingRound"])
        assert fishing_state["cast_count"] == casts
    finally:
        fishing_state.clear()
        fishing_state.update(saved)
