# -*- coding: utf-8 -*-
"""绿野寻仙踪独立任务与日常买鱼流水线契约测试。"""
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "assets/resource/pipeline/features/green_wild.json"
OPEN_SHELL_PATH = ROOT / "assets/resource/pipeline/features/open_shell.json"
IMAGE_DIR = ROOT / "assets/resource/image"
GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def run_tests():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    open_shell = json.loads(OPEN_SHELL_PATH.read_text(encoding="utf-8"))

    assert business_next(pipeline["GreenWildTask"]) == ["GreenWildStartRouter"]
    assert business_next(pipeline["GreenWildStartRouter"]) == [
        "GreenWildClaimAll",
        "GreenWildOpenTask",
        "GreenWildOpenTaskByOcr",
        "GreenWildEntry",
        "GreenWildAbort",
    ]
    assert pipeline["GreenWildEntry"]["template"] == "绿野寻仙踪_入口.png"
    assert pipeline["GreenWildEntry"]["roi"] == [120, 258, 90, 90]
    assert pipeline["GreenWildEntry"]["action"] == "Click"
    assert "target" not in pipeline["GreenWildEntry"]
    assert pipeline["GreenWildEntry"]["post_delay"] == 3000
    assert business_next(pipeline["GreenWildEntry"]) == ["GreenWildPageWait"]
    assert pipeline["GreenWildPageWait"]["post_delay"] == 2000
    assert business_next(pipeline["GreenWildPageWait"]) == [
        "GreenWildClaimAll",
        "GreenWildOpenTask",
        "GreenWildOpenTaskByOcr",
        "GreenWildReturn",
    ]
    assert pipeline["GreenWildOpenTask"]["template"] == "绿野寻仙踪_任务.png"
    assert pipeline["GreenWildOpenTask"]["roi"] == [20, 300, 140, 140]
    assert pipeline["GreenWildOpenTask"]["action"] == "Click"
    assert "target" not in pipeline["GreenWildOpenTask"]
    assert business_next(pipeline["GreenWildOpenTask"]) == [
        "GreenWildClaimAll",
        "GreenWildReturn",
    ]
    assert pipeline["GreenWildOpenTask"].get("on_error") == ["GreenWildOpenTaskByOcr"]
    ocr_task = pipeline["GreenWildOpenTaskByOcr"]
    assert ocr_task["recognition"] == "OCR"
    assert ocr_task["expected"] == "^任务$"
    assert ocr_task["roi"] == [20, 300, 140, 140]
    assert ocr_task["action"] == "Click"
    assert "target" not in ocr_task
    assert business_next(ocr_task) == ["GreenWildClaimAll", "GreenWildReturn"]
    claim = pipeline["GreenWildClaimAll"]
    assert claim["recognition"] == "OCR"
    assert claim["expected"] == "键领取"
    assert claim["roi"] == [1050, 540, 200, 90]
    assert claim["action"] == "Click"
    assert "target" not in claim
    assert business_next(claim) == ["GreenWildReturn"]
    assert claim.get("on_error") == ["GreenWildReturn"]
    assert pipeline["GreenWildReturn"]["template"] == "绿野寻仙踪_返回.png"
    assert pipeline["GreenWildReturn"]["roi"] == [1140, 20, 130, 100]
    assert pipeline["GreenWildReturn"]["action"] == "Click"
    assert "target" not in pipeline["GreenWildReturn"]
    assert pipeline["GreenWildVerifyTank"]["template"] == "主界面特征.png"

    assert pipeline["GreenWildDailyTask"]["custom_action"] == "InitGreenWildDailyAction"
    assert business_next(pipeline["GreenWildDailyTask"]) == [
        "OpenShellStartPage",
        "OpenShellCategoryPage",
        "OpenShellEntry",
        "OpenShellAbort",
    ]
    assert business_next(open_shell["OpenShellVerifyMainAfterDone"]) == [
        "GreenWildDailyBuyFishEntry",
        "OpenShellStandaloneComplete",
    ]
    assert pipeline["GreenWildDailyBuyFishEntry"]["custom_recognition"] == "CheckGreenWildDailyPendingReco"
    assert pipeline["GreenWildDailyOpenShop"]["template"] == "买鱼入口.png"
    assert pipeline["GreenWildDailyOpenShop"]["roi"] == [1171, 497, 44, 37]
    assert pipeline["GreenWildDailySelectShellFish"]["expected"] == "^贝币鱼儿$"
    assert pipeline["GreenWildDailySelectShellFish"]["roi"] == [411, 119, 116, 34]
    assert pipeline["GreenWildDailyClickFishCard"]["recognition"] == "DirectHit"
    assert pipeline["GreenWildDailyClickFishCard"]["action"] == "Click"
    assert pipeline["GreenWildDailyClickFishCard"]["target"] == [93, 295, 208, 180]
    assert pipeline["GreenWildDailyPurchase"]["expected"] == "^购买$"
    assert pipeline["GreenWildDailyPurchase"]["roi"] == [856, 521, 81, 38]
    assert pipeline["GreenWildDailyContinue"]["expected"] == "^继续购物$"
    assert pipeline["GreenWildDailyContinue"]["roi"] == [360, 543, 181, 39]
    assert pipeline["GreenWildDailyReturn1"]["expected"] == "^返回$"
    assert pipeline["GreenWildDailyReturn1"]["roi"] == [57, 28, 82, 45]
    assert pipeline["GreenWildDailyReturn2"]["expected"] == "^返回$"
    assert pipeline["GreenWildDailyReturn2"]["roi"] == [57, 28, 82, 45]
    assert pipeline["GreenWildDailyVerifyTank"]["custom_action"] == "GreenWildDailyDoneAction"
    assert business_next(pipeline["GreenWildDailyVerifyTank"]) == [
        "DailyRoutineReturnIfActive",
        "DailyRoutineStandaloneDone",
    ]

    for node_name, node in pipeline.items():
        successors = node.get("next")
        if successors:
            assert successors[:len(GLOBAL_HANDLERS)] == GLOBAL_HANDLERS, node_name

    for name in (
        "绿野寻仙踪_入口.png",
        "绿野寻仙踪_任务.png",
        "绿野寻仙踪_返回.png",
        "买鱼入口.png",
    ):
        assert (IMAGE_DIR / name).is_file(), f"missing template: {name}"
        width, height = png_size(IMAGE_DIR / name)
        for node in pipeline.values():
            if node.get("template") == name:
                _, _, roi_w, roi_h = node["roi"]
                assert width <= roi_w and height <= roi_h, f"{name} {width}x{height} exceeds {roi_w}x{roi_h}"

    interface_paths = [
        ROOT / "assets/interface.json",
        ROOT / "client/interface.json",
        ROOT / "client_avalonia/interface.json",
    ]
    interface_bytes = [path.read_bytes() for path in interface_paths]
    assert interface_bytes[0] == interface_bytes[1] == interface_bytes[2]
    interface = json.loads(interface_bytes[0].decode("utf-8"))
    green_wild_tasks = [task for task in interface["task"] if task["entry"] == "GreenWildTask"]
    assert len(green_wild_tasks) == 1
    assert green_wild_tasks[0]["name"] == "绿野寻仙踪"
    assert green_wild_tasks[0]["default_check"] is False
    routine_cases = {
        case["name"] for case in interface["option"]["日常收尾任务"]["cases"]
    }
    assert "绿野寻仙踪日常" in routine_cases
    assert "绿野寻仙踪日常" not in interface["option"]["日常收尾任务"]["default_case"]

    from agent.runtime_state import daily_routine_state, green_wild_daily_state
    from agent.my_reco import CheckGreenWildDailyPendingReco
    from agent.my_action import InitGreenWildDailyAction, GreenWildDailyDoneAction

    class MockArg:
        def __init__(self, param=None):
            self.custom_action_param = json.dumps(param or {})
            self.custom_recognition_param = self.custom_action_param

    class MockContext:
        def override_pipeline(self, data):
            self.override = data

    reco = CheckGreenWildDailyPendingReco()
    daily_routine_state["active"] = False
    daily_routine_state["step"] = "GREEN_WILD_DAILY"
    green_wild_daily_state["pending_buy_fish"] = True
    assert reco.analyze(MockContext(), MockArg()) is None

    daily_routine_state["active"] = True
    daily_routine_state["step"] = "GOLD_SHELL_COUPON"
    assert reco.analyze(MockContext(), MockArg()) is None

    daily_routine_state["step"] = "GREEN_WILD_DAILY"
    green_wild_daily_state["pending_buy_fish"] = False
    assert reco.analyze(MockContext(), MockArg()) is None

    ctx = MockContext()
    assert InitGreenWildDailyAction().run(ctx, MockArg()) is True
    assert green_wild_daily_state["pending_buy_fish"] is True
    assert reco.analyze(ctx, MockArg()) == (0, 0, 10, 10)
    assert ctx.override["OpenShellShouldContinue"]["custom_recognition_param"]["target_count"] == 1

    daily_routine_state["tasks"]["GreenWildDaily"] = {"status": "IDLE"}
    daily_routine_state["queue"] = ["GOLDEN_DOLPHIN"]
    assert GreenWildDailyDoneAction().run(ctx, MockArg()) is True
    assert green_wild_daily_state["pending_buy_fish"] is False
    assert daily_routine_state["step"] == "GOLDEN_DOLPHIN"
    daily_routine_state["active"] = False

    print("[PASS] GreenWildTask and GreenWildDaily buy-fish contract")


if __name__ == "__main__":
    run_tests()
