#!/usr/bin/env python3
"""Offline topology contracts for resumable standalone task starts."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "assets/resource/pipeline"
GLOBAL = {
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
}


def load(relative):
    return json.loads((PIPELINE / relative).read_text(encoding="utf-8"))


def business_next(node):
    return [item for item in node.get("next", []) if item not in GLOBAL]


def test_sea_dive_deepest_first_resume_order():
    p = load("features/sea_dive.json")
    assert business_next(p["SeaDiveStartRouter"]) == [
        "SeaDiveRetentionWait",
        "SeaDiveResultPage",
        "SeaDiveInGame",
        "SeaDiveDepthSelectPage",
        "SeaDiveStartAtHome",
        "SeaDiveStartAtPicker",
        "SeaDiveStartAtTank3",
        "SeaDiveStartAtTank1",
        "SeaDiveStartAtTank2",
        "SeaDiveAbortUnknownPage",
    ]


def test_open_shell_resumes_half_finished_round_before_ready_page():
    p = load("features/open_shell.json")
    route = business_next(p["OpenShellStartRouter"])
    assert route[:4] == [
        "OpenShellOctopus",
        "OpenShellFinish",
        "OpenShellContinue",
        "OpenShellOpenFirst",
    ]
    assert route.index("OpenShellOpenFirst") < route.index("OpenShellStartPage")


def test_starfish_only_clicks_settings_after_numbered_tank_gate():
    p = load("collect_fish.json")
    route = business_next(p["FeedStarfishStandaloneStartRouter"])
    assert route == [
        "VerifyStarfishPanel_Standalone",
        "VerifyTankSettings_Standalone",
        "FeedStarfishOpenManagementFromTank1",
        "FeedStarfishOpenManagementFromTank2",
        "FeedStarfishOpenManagementFromTank3",
        "FeedStarfishStandaloneAbort",
    ]
    for tank in (1, 2, 3):
        node = p[f"FeedStarfishOpenManagementFromTank{tank}"]
        assert node["recognition"] == "TemplateMatch"
        assert node["template"] == f"patrol/鱼缸{tank}_主页面编号.png"
        assert node["target"] == [176, 54, 4, 4]
    assert p["FeedStarfishStandaloneAbort"]["action"] == "StopTask"


def test_minigame_settlement_resume_routes_to_exit_once():
    golden = load("features/golden_dolphin.json")
    shake = load("features/shake_game.json")
    assert business_next(golden["GoldenDolphinNavigation"])[0] == "GoldenDolphinResumeSettlement"
    assert golden["GoldenDolphinResumeSettlement"]["next"] == ["GoldenDolphinExit"]
    assert business_next(shake["ShakeGameNavigation"])[0] == "ShakeGameResumeSettlement"
    assert shake["ShakeGameResumeSettlement"]["next"] == ["ShakeGameExit"]


def test_band_fish_resumes_safe_contexts_and_aborts_unknown():
    p = load("features/band_fish.json")
    route = business_next(p["BandFishStartRouter"])
    assert route[:3] == [
        "BandFishStartAtSettlement",
        "BandFishStartAtPlaying",
        "BandFishStartAtScoreDialog",
    ]
    assert p["BandFishStartAtScoreDialog"]["custom_action"] == "BandFishPerformAction"
    assert p["BandFishStartUnknown"]["action"] == "StopTask"

    interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
    for case in interface["option"]["乐队鱼乐章"]["cases"]:
        override = case["pipeline_override"]
        assert override["BandFishStartAtScoreDialog"]["custom_action_param"] == (
            override["BandFishCheckReady"]["custom_action_param"]
        )


def test_princess_resumes_result_dialogs_before_pages():
    p = load("features/princess_task.json")
    assert business_next(p["PrincessStartRouter"])[:3] == [
        "PrincessTreasureClaimSuccess",
        "PrincessClaimSuccess",
        "PrincessClaimFailure",
    ]


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
