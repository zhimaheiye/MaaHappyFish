# -*- coding: utf-8 -*-
"""挂机到点插入日常收尾 / 好友摸宝契约测试。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.runtime_state import daily_routine_state, hangup_schedule_state
from agent.my_reco import (
    CheckHangupNoonDailyDueReco,
    CheckHangupFriendGemDueReco,
    CheckHangupResumeReco,
)
from agent.my_action import InitHangupScheduledDailyAction, HangupPopResumeAction

ROOT = Path(__file__).resolve().parents[1]
GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]


class MockArg:
    def __init__(self, param=None):
        self.custom_action_param = json.dumps(param or {})
        self.custom_recognition_param = json.dumps(param or {})


class MockContext:
    def get_node_data(self, name):
        return {}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


def reset_state():
    hangup_schedule_state["resume_stack"] = []
    hangup_schedule_state["noon_daily_last_date"] = None
    hangup_schedule_state["friend_gem_morning_date"] = None
    hangup_schedule_state["friend_gem_evening_date"] = None
    daily_routine_state["active"] = False


def test_reco_windows():
    reset_state()
    noon = CheckHangupNoonDailyDueReco()
    friend = CheckHangupFriendGemDueReco()
    ctx = MockContext()

    assert noon.analyze(ctx, MockArg({"enabled": False, "now": "2026-09-17T12:00:00"})) is None
    assert noon.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T11:59:00"})) is None
    assert noon.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T12:00:00"})) == (0, 0, 10, 10)
    hangup_schedule_state["noon_daily_last_date"] = "2026-09-17"
    assert noon.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T15:00:00"})) is None
    hangup_schedule_state["noon_daily_last_date"] = None
    daily_routine_state["active"] = True
    assert noon.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T12:00:00"})) is None
    daily_routine_state["active"] = False

    assert friend.analyze(ctx, MockArg({"enabled": False, "now": "2026-09-17T10:00:00"})) is None
    assert friend.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T09:59:00"})) is None
    assert friend.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T10:00:00"})) == (0, 0, 10, 10)
    assert friend.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T12:00:00"})) is None
    assert friend.analyze(ctx, MockArg({"enabled": True, "now": "2026-09-17T22:00:00"})) == (0, 0, 10, 10)
    print("[PASS] hang-up due windows")


def test_resume_stack():
    reset_state()
    ctx = MockContext()
    InitHangupScheduledDailyAction().run(ctx, MockArg({"resume_to": "collect_fish"}))
    assert hangup_schedule_state["resume_stack"] == ["collect_fish"]
    assert daily_routine_state.get("active") is True
    reco = CheckHangupResumeReco()
    assert reco.analyze(ctx, MockArg({"target": "collect_fish"})) == (0, 0, 10, 10)
    assert reco.analyze(ctx, MockArg({"target": "patrol"})) is None
    HangupPopResumeAction().run(ctx, MockArg())
    assert hangup_schedule_state["resume_stack"] == []
    print("[PASS] hang-up resume stack")


def test_pipeline_wiring():
    collect = json.loads((ROOT / "assets/resource/pipeline/collect_fish.json").read_text(encoding="utf-8"))
    patrol = json.loads((ROOT / "assets/resource/pipeline/features/patrol.json").read_text(encoding="utf-8"))
    friend = json.loads((ROOT / "assets/resource/pipeline/features/friend_gem.json").read_text(encoding="utf-8"))
    daily = json.loads((ROOT / "assets/resource/pipeline/routine/daily_routine.json").read_text(encoding="utf-8"))
    hangup = json.loads((ROOT / "assets/resource/pipeline/routine/hangup_schedule.json").read_text(encoding="utf-8"))

    harvest_next = collect["ResumeHarvest"]["next"]
    assert harvest_next.index("HangupNoonDailyCollectFish") < harvest_next.index("HangupFriendGemCollectFish")
    assert harvest_next.index("HangupFriendGemCollectFish") < harvest_next.index("TriggerStarfishFeed")

    wait_next = patrol["PatrolWaitLoop"]["next"]
    assert wait_next.index("HangupNoonDailyPatrol") < wait_next.index("HangupFriendGemPatrol")
    assert wait_next.index("HangupFriendGemPatrol") < wait_next.index("PatrolTimerDue")

    assert "HangupNoonDailyFriendGem" in friend["FriendGemFriendRouter"]["next"]
    assert business_next(friend["FriendGemDone"]) == [
        "HangupResumeCollectFish",
        "HangupResumePatrol",
    ]
    assert business_next(daily["DailyRoutineStepAllDone"]) == [
        "HangupResumeCollectFish",
        "HangupResumePatrol",
        "HangupResumeFriendGem",
        "DailyRoutineStandaloneDone",
    ]
    assert business_next(hangup["HangupNoonDailyCollectFish"]) == ["HangupPrepareDaily"]
    assert business_next(hangup["HangupPrepareDaily"]) == [
        "HangupDailyOnTank",
        "HangupDailyClickReturn",
    ]
    assert business_next(hangup["HangupDailyOnTank"]) == ["DailyRoutineInitLog"]
    assert hangup["HangupNoonDailyCollectFish"]["custom_recognition_param"]["enabled"] is True
    assert hangup["HangupFriendGemCollectFish"]["custom_recognition_param"]["enabled"] is False
    print("[PASS] hang-up pipeline wiring")


def test_interface_options():
    interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
    collect = next(task for task in interface["task"] if task["entry"] == "CollectFishTask")
    patrol = next(task for task in interface["task"] if task["entry"] == "PatrolTask")
    friend = next(task for task in interface["task"] if task["entry"] == "FriendGemTask")
    assert "挂机十二点日常" in collect["option"]
    assert "挂机十点好友摸宝" in collect["option"]
    assert "挂机十二点日常" in patrol["option"]
    assert "挂机十点好友摸宝" in patrol["option"]
    assert "挂机十二点日常" in friend["option"]
    assert interface["option"]["挂机十二点日常"]["default_case"] == "开启"
    assert interface["option"]["挂机十点好友摸宝"]["default_case"] == "关闭"
    print("[PASS] hang-up interface options")


if __name__ == "__main__":
    test_reco_windows()
    test_resume_stack()
    test_pipeline_wiring()
    test_interface_options()
    print("[ALL PASS] hang-up schedule")
