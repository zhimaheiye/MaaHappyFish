import json
from pathlib import Path


PIPELINE_DIR = Path("assets/resource/pipeline")
GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]
HANDLER_NODES = {
    "GlobalActivityPagePopup",
    "GlobalDailySignPopup",
    "GlobalDailySignClaim",
    "GlobalDailySignClaimByOcr",
    "GlobalSpecialOfferPopup",
    "GlobalNewsPopup",
    "GlobalLevelUpPopup",
}
ISOLATED_PIPELINES = {"mobile_ads.json", "emulator_ads.json"}
ATOMIC_NEXT_NODES = {
    "ClickFishBubble",
    "SweepFishTankBottomAfterBubble",
    "PatrolCollectTank1Bubble",
    "PatrolSweepTank1AfterBubble",
    "PatrolCollectTank2Bubble",
    "PatrolSweepTank2AfterBubble",
    "PatrolCollectTank3Bubble",
    "PatrolSweepTank3AfterBubble",
    "ShakeGemCollectSweepBottom",
}
INTERNAL_CHAIN_NODES = {
    "CollectFishDualStartAtTank1",
    "CollectFishDualStartAtTank2",
    "CollectFishDualStartAtTank3",
    "CollectFishDualStartAtPicker",
    "CollectFishVerifyTank1MainDualStart",
    "CollectFishSingleStartTank1",
    "CollectFishSingleStartTank2",
    "CollectFishSingleStartTank3",
    "CollectFishSingleStartFallback",
    "CollectFishStarfishEntryUnknown",
    "CollectFishStarfishEntryRetry",
    "CollectFishStarfishEntryRetryRouter",
    "CollectFishStarfishEntryCanRetry",
    "CollectFishStarfishEntryFailed",
    "CollectFishStarfishEntryFailedNeedsInitialization",
    "CollectFishExitManagementFail",
    "CollectFishStarfishFlowFailed",
    "CollectFishSwitchToTank2Target",
    "CollectFishVerifyTank2Main",
    "CollectFishSwitchToTank1Target",
    "CollectFishVerifyTank1Main",
    "CollectFishSwitchRetry",
    "DailyRoutineInitLog",
}


def load_pipeline():
    merged = {}
    locations = {}
    for path in sorted(PIPELINE_DIR.rglob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        for name, node in data.items():
            assert name not in merged, f"duplicate node: {name}"
            merged[name] = node
            locations[name] = path
    return merged, locations


def run_tests():
    pipeline, locations = load_pipeline()

    activity_page = pipeline["GlobalActivityPagePopup"]
    assert activity_page["template"] == "活动页面_退出.png"
    assert activity_page["roi"] == [0, 0, 136, 116]
    assert activity_page["action"] == "Click"
    assert "target" not in activity_page

    popup = pipeline["GlobalDailySignPopup"]
    assert popup["template"] == "签到_识别.png"
    assert popup["action"] == "DoNothing"
    assert popup["next"] == ["GlobalDailySignClaim"]

    claim = pipeline["GlobalDailySignClaim"]
    assert claim["template"] == "签到_点击.png"
    assert claim["action"] == "Click"
    assert claim["roi"] == [0, 400, 1280, 320]
    assert "target" not in claim
    assert claim["next"] == ["GlobalDailySignClose", "GlobalDailySignAutoClosed"]
    assert claim["on_error"] == ["GlobalDailySignClaimByOcr"]

    claim_ocr = pipeline["GlobalDailySignClaimByOcr"]
    assert claim_ocr["recognition"] == "OCR"
    assert claim_ocr["expected"] == "^签到$"
    assert claim_ocr["roi"] == [0, 400, 1280, 320]
    assert claim_ocr["action"] == "Click"
    assert claim_ocr["next"] == ["GlobalDailySignClose", "GlobalDailySignAutoClosed"]
    assert claim_ocr["on_error"] == ["GlobalDailySignClose"]

    close = pipeline["GlobalDailySignClose"]
    assert close["template"] == "签到_关闭.png"
    assert close["roi"] == [1000, 0, 220, 160]
    assert close["action"] == "Click"
    assert "target" not in close

    auto_closed = pipeline["GlobalDailySignAutoClosed"]
    assert auto_closed["template"] == "签到_识别.png"
    assert auto_closed["inverse"] is True
    assert auto_closed["action"] == "DoNothing"

    assert pipeline["DailySignTask"]["next"] == [
        *GLOBAL_HANDLERS,
        "DailySignNoPopup",
    ]

    offer = pipeline["GlobalSpecialOfferPopup"]
    assert offer["template"] == "特惠礼包_识别.png"
    assert offer["action"] == "DoNothing"
    assert offer["next"] == ["GlobalSpecialOfferClose"]

    offer_close = pipeline["GlobalSpecialOfferClose"]
    assert offer_close["template"] == "特惠礼包_关闭.png"
    assert offer_close["action"] == "Click"
    assert "target" not in offer_close

    news = pipeline["GlobalNewsPopup"]
    assert news["recognition"] == "OCR"
    assert news["expected"] == "快报"
    assert news["roi"] == [635, 23, 226, 162]
    assert news["action"] == "DoNothing"
    assert news["next"] == ["GlobalNewsClose"]

    news_close = pipeline["GlobalNewsClose"]
    assert news_close["template"] == "快报页面_关闭.png"
    assert news_close["roi"] == [1044, 77, 26, 31]
    assert news_close["action"] == "Click"
    assert "target" not in news_close

    level_up = pipeline["GlobalLevelUpPopup"]
    assert level_up["recognition"] == "TemplateMatch"
    assert level_up["template"] == "升级弹窗_识别.png"
    assert level_up["roi"] == [200, 348, 378, 185]
    assert level_up["action"] == "DoNothing"
    assert level_up["next"] == ["GlobalLevelUpConfirm"]

    level_up_confirm = pipeline["GlobalLevelUpConfirm"]
    assert level_up_confirm["recognition"] == "OCR"
    assert level_up_confirm["expected"] == "太好了"
    assert level_up_confirm["roi"] == [957, 627, 125, 47]
    assert level_up_confirm["action"] == "Click"
    assert "target" not in level_up_confirm

    missing = []
    for name, node in pipeline.items():
        if locations[name].name in ISOLATED_PIPELINES:
            continue
        successors = node.get("next")
        if name in HANDLER_NODES or name in ATOMIC_NEXT_NODES or name in INTERNAL_CHAIN_NODES or not successors:
            continue
        if successors[:len(GLOBAL_HANDLERS)] != GLOBAL_HANDLERS:
            missing.append(f"{locations[name]}::{name}")
    assert not missing, "global popup handlers are not first:\n" + "\n".join(missing)

    image_dir = Path("assets/resource/image")
    for template in (
        "活动页面_退出.png",
        "签到_识别.png",
        "签到_点击.png",
        "签到_关闭.png",
        "特惠礼包_识别.png",
        "特惠礼包_关闭.png",
        "快报页面_关闭.png",
        "升级弹窗_识别.png",
    ):
        assert (image_dir / template).is_file(), f"missing template: {template}"

    print(
        "[PASS] global activity-page, daily-sign, special-offer, news, "
        "and level-up handlers"
    )


if __name__ == "__main__":
    run_tests()
