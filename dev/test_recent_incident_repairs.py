from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from agent import my_action


class _WaitJob:
    def __init__(self, result=None):
        self.result = result
        self.waited = False

    def wait(self):
        self.waited = True
        return self

    def get(self):
        assert self.waited, "fresh screencap result must not be read before wait()"
        return self.result


class _GoldenController:
    def __init__(self, frame):
        self.frame = frame
        self.capture_jobs = []
        self.clicks = []

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return _WaitJob()

    def post_screencap(self):
        job = _WaitJob(self.frame)
        self.capture_jobs.append(job)
        return job


def test_golden_dolphin_confirmation_waits_for_fresh_frame():
    controller = _GoldenController(np.zeros((720, 1280, 3), dtype=np.uint8))
    template = np.zeros((20, 20, 3), dtype=np.uint8)
    with patch.object(my_action.time, "sleep"), patch.object(
        my_action.cv2, "matchTemplate", return_value=np.array([[0.1]], dtype=np.float32)
    ):
        closed, _x, _y = my_action._confirm_golden_dolphin_dialog_closed(
            controller, template, None, 824, 480
        )
    assert closed is True
    assert controller.clicks == [(824, 480)]
    assert controller.capture_jobs[0].waited is True


def test_recent_round_reset_and_close_nodes_click_recognized_centers():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    patrol = json.loads(
        (root / "assets/resource/pipeline/features/patrol.json").read_text(encoding="utf-8")
    )
    for tank in (2, 3):
        for suffix in ("", "RetryClick"):
            node = patrol[f"PatrolCycleResetTank{tank}{suffix}"]
            assert node["action"] == "Custom"
            assert node["custom_action"] == "ClickRecognizedCenterAction"

    sea_dive = json.loads(
        (root / "assets/resource/pipeline/features/sea_dive.json").read_text(encoding="utf-8")
    )
    for name in ("SeaDiveHomeClose", "SeaDiveVerifyExitTank3", "SeaDiveVerifyExitTank2"):
        assert sea_dive[name]["action"] == "Custom"
        assert sea_dive[name]["custom_action"] == "ClickRecognizedCenterAction"


def test_shake_navigation_requires_main_tank_before_opening_panel():
    templates = my_action._get_shake_game_templates()
    assert templates["main"] is not None
    source = __import__("inspect").getsource(my_action.ShakeGameNavigationAction.run)
    assert "main_score < 0.70" in source
    assert "当前既非游乐园面板也未确认主鱼缸" in source


def test_sea_otter_user_stop_during_boundary_recheck_is_not_logged_as_error():
    action = my_action.SeaOtterReturnFromRecommendedAction()
    controller = SimpleNamespace()

    class _Hit:
        hit = True

    class _Miss:
        hit = False

    results = {
        "SeaOtterRecommendedBridge": _Hit(),
        "SeaOtterHasStaminaPanel": _Miss(),
        "SeaOtterFriendLiked": _Miss(),
        "SeaOtterFriendUnliked": _Miss(),
    }
    context = SimpleNamespace(
        tasker=SimpleNamespace(controller=controller),
        run_recognition=lambda name, _frame: results[name],
    )
    my_action.sea_otter_gem_state["current_side"] = "left"
    printed = []
    with patch.object(my_action, "_task_cancelled", side_effect=[False, True]), patch.object(
        my_action, "_capture_720p", return_value=np.zeros((720, 1280, 3), dtype=np.uint8)
    ), patch("builtins.print", side_effect=lambda *args, **_kwargs: printed.append(" ".join(map(str, args)))):
        assert action.run(context, SimpleNamespace(custom_action_param="null")) is False
    assert not any("ERROR" in line for line in printed)
