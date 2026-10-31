"""Evidence-backed return gates and development dependency isolation; no UI."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action, dev_environment
from agent.my_reco import FishBabyHomePageReco
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


@pytest.mark.parametrize("pages,expected_clicks,success", [
    (["tank", "tank"], [], True),
    (["performance", "tank", "tank"], [(90, 45)], True),
    (["performance", "grid", "tank", "tank"], [(90, 45), (640, 150)], True),
    (["performance", "performance", "performance", "tank", "tank"], [(90, 45)], True),
    (["grid", "tank", "tank"], [(640, 150)], True),
    (["unknown"], [], False),
    (["performance"], [(90, 45)], False),
    (["starfish"], [], False),
    (["stopped"], [], False),
])
def test_band_exit_confirms_tank_before_advancing(pages, expected_clicks, success):
    saved = copy.deepcopy(my_action.daily_routine_state)
    saved_band = copy.deepcopy(my_action.band_fish_state)
    clicks = []
    now = [0.0]
    frames = {name: np.full((720, 1280, 3), i, np.uint8)
              for i, name in enumerate(set(pages))}
    page_by_pixel = {int(im[0, 0, 0]): name for name, im in frames.items()}
    remaining = list(pages)

    class Job:
        failed = False
        def wait(self): return self
        def get(self):
            page = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return frames[page]

    class Controller:
        def post_screencap(self): return Job()
        def post_click(self, x, y):
            clicks.append((x, y))
            return Job()

    def recognize(name, frame):
        page = page_by_pixel[int(frame[0, 0, 0])]
        hit = (name, page) in {
            ("BandFishStartAtMyPerformance", "performance"),
            ("BandFishExitReturn", "performance"),
            ("BandFishStartAtAmusementGrid", "grid"),
            ("BandFishStartAtTank", "tank"),
        }
        return SimpleNamespace(hit=hit, box=(50, 25, 80, 40))

    def sleep(seconds): now[0] += seconds
    context = SimpleNamespace(tasker=SimpleNamespace(
        running=True, stopping=pages == ["stopped"], controller=Controller()), run_recognition=recognize)
    try:
        my_action.daily_routine_state.update(active=True, step="BAND_FISH_PASS1", queue=["FREE_GIFT"],
            tasks={"BandFish": {"stage": "PASS1", "status": "IDLE"}})
        my_action.band_fish_state.update(status="DONE", performance_finished=True)
        with patch.object(my_action.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(my_action.time, "sleep", side_effect=sleep):
            result = my_action.BandFishExitToTankAction().run(context, SimpleNamespace(custom_action_param="null"))
        assert result is success
        assert clicks == expected_clicks
        assert my_action.daily_routine_state["step"] == ("FREE_GIFT" if success else "BAND_FISH_PASS1")
    finally:
        my_action.daily_routine_state.clear(); my_action.daily_routine_state.update(saved)
        my_action.band_fish_state.clear(); my_action.band_fish_state.update(saved_band)


def test_release_directory_does_not_select_development_dependencies(tmp_path):
    original = list(sys.path)
    assert dev_environment.configure_development_imports(tmp_path / "agent/main.py") is None
    assert sys.path == original


def test_wrong_development_python_is_rejected(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/interface.json").write_text("{}")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/pyvenv.cfg").write_text("version = 0.0.1")
    with pytest.raises(RuntimeError, match="Python version"):
        dev_environment.configure_development_imports(tmp_path / "agent/main.py")


@pytest.mark.skipif(not (ROOT / ".venv/pyvenv.cfg").is_file(), reason="Requires the local development venv")
def test_global_python_uses_checkout_maa_without_starting_agent():
    global_python = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
    code = """import sys, importlib.metadata
from agent.dev_environment import configure_development_imports
site = configure_development_imports('agent/main.py')
import maa
print(site)
print(importlib.metadata.version('maafw'))
assert str(site) in str(maa.__file__)
"""
    result = subprocess.run([str(global_python), "-c", code], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "5.12.3" in result.stdout


def read_frame(name):
    path = ROOT / "dev/fixtures/stability_20261031" / name
    frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None
    return frame


@pytest.mark.parametrize("case", ["recharge", "negative", "green_missing"])
def test_native_recharge_tab_and_green_preflight(case):
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/stability-20261031-native"))
    positive = case == "recharge"
    frame = read_frame({"recharge": "recharge_tab.png", "negative": "starfish.png",
                        "green_missing": "green_entry_missing.png"}[case])
    reached = []

    class Controller(CustomController):
        def connect(self): return True
        def request_uuid(self): return "offline-stability-20261031"
        def get_features(self): return 0
        def screencap(self): return frame
        def click(self, x, y): raise AssertionError("Replay never clicks")

    class Record(CustomAction):
        def run(self, context, argv):
            reached.append(argv.node_name)
            return True

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    assert resource.register_custom_action("OfflineStabilityRecord", Record())
    assert resource.register_custom_action("FailTaskAction", my_action.FailTaskAction())
    assert resource.override_pipeline({
        "DailyFreeGiftStartRouter": {"timeout": 0},
        "DailyFreeGiftRechargePage": {"action": "Custom", "custom_action": "OfflineStabilityRecord", "next": [], "on_error": []},
        "GreenWildDailyPreflight": {"timeout": 0},
        "OpenShellStartRouter": {"action": "Custom", "custom_action": "OfflineStabilityRecord", "next": []},
    })
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    result = tasker.post_task("GreenWildDailyPreflight" if case == "green_missing" else "DailyFreeGiftStartRouter").wait()
    assert result.succeeded is positive
    assert reached == (["DailyFreeGiftRechargePage"] if positive else [])


def test_baby_entry_waits_for_home_without_retrying_known_old_tank():
    nodes = json.loads((ROOT / "assets/resource/pipeline/features/fish_baby.json").read_text(encoding="utf-8"))
    router = nodes["FishBabyEntryRouter"]
    assert router["timeout"] == 8000
    assert router["next"] == ["FishBabyAtHome"]
    assert router["on_error"] == ["FishBabyAtHome", "FishBabyMainTankSky", "FishBabyAbort"]
    # The actual error frame is already HOME when the old sky candidate times out.
    frame = read_frame("baby_home.png")
    assert FishBabyHomePageReco().analyze(None, SimpleNamespace(image=frame)) is not None


def test_native_baby_home_can_arrive_after_entry_router_starts():
    Library.open(Library.framework_libpath.parent, agent_server=False)
    Toolkit.init_option(str(ROOT / "temp/stability-20261031-native"))
    home = read_frame("baby_home.png")
    read = [0]
    reached = []

    class Controller(CustomController):
        def connect(self): return True
        def request_uuid(self): return "offline-delayed-baby-home"
        def get_features(self): return 0
        def screencap(self):
            read[0] += 1
            return np.zeros_like(home) if read[0] < 3 else home
        def click(self, x, y): raise AssertionError("Delayed HOME must not trigger extra entry clicks")

    class Record(CustomAction):
        def run(self, context, argv):
            reached.append(argv.node_name)
            return True

    resource = Resource()
    assert resource.post_bundle(ROOT / "assets/resource").wait().succeeded
    assert resource.register_custom_recognition("FishBabyHomePageReco", FishBabyHomePageReco())
    assert resource.register_custom_action("OfflineStabilityRecord", Record())
    assert resource.register_custom_action("FailTaskAction", my_action.FailTaskAction())
    assert resource.override_pipeline({
        "FishBabyEntryRouter": {"rate_limit": 10, "timeout": 1500},
        "FishBabyAtHome": {"action": "Custom", "custom_action": "OfflineStabilityRecord", "next": []},
    })
    controller = Controller()
    assert controller.post_connection().wait().succeeded
    tasker = Tasker()
    assert tasker.bind(resource, controller)
    assert tasker.post_task("FishBabyEntryRouter").wait().succeeded
    assert read[0] >= 3
    assert reached == ["FishBabyAtHome"]
