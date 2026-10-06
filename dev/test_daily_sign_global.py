import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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
    "GlobalActivityPageReturn",
    "GlobalLuckyMomentClose",
    "FriendPageMessageBoxToStarFriends",
    "GlobalDailySignPopup",
    "GlobalDailySignAlreadySigned",
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
    "CollectFishStarfishEntryUnknown",
    "CollectFishStarfishEntryRetry",
    "CollectFishStarfishEntryRetryRouter",
    "CollectFishStarfishEntryCanRetry",
    "CollectFishStarfishEntryFailed",
    "CollectFishStarfishEntryFailedNeedsInitialization",
    "CollectFishExitManagementFail",
    "CollectFishFoodNotRecognized",
    "CollectFishStarfishFlowFailed",
    "CollectFishSwitchToTank2Target",
    "CollectFishVerifyTank2Main",
    "CollectFishSwitchToTank1Target",
    "CollectFishVerifyTank1Main",
    "CollectFishSwitchRetry",
    "DailyRoutineInitLog",
}

# Explicit page-local contracts, not whole-file exemptions. These chains use
# their own visual gates/failure exits; inserting JumpBack at every intermediate
# node can leave the business page and resume an invalid stage. New nodes still
# require review. See docs/features/daily-sign.md.
PAGE_LOCAL_CHAINS = {
    # Message policy is a one-shot parameter chain. The inbox action owns the
    # page gate and only then returns through JumpBack to the start router.
    "friend_gem.json": {
        "FriendGemMessagePolicySystem", "FriendGemMessagePolicyFriendRequest",
        "FriendGemMessagePolicyBabyVisit", "FriendGemMessagePolicyCoupon",
        "FriendGemMessagePolicyOther", "FriendGemMessageInbox",
    },
    # Home return must keep the blue back button; a global activity JumpBack
    # can steal it before the tank template is checked.
    "sea_otter_gem.json": {
        "SeaOtterHomeReturnRouter", "SeaOtterUnusedStaminaDialog",
        "SeaOtterHomeAtTank", "SeaOtterHomeAtPet", "SeaOtterHomeAtFriendList",
        "SeaOtterHomeAtFriendTank", "SeaOtterHomeClickBack", "SeaOtterHomeReturnWait",
    },
    # Custom actions finish/resume a visually verified performance or settlement.
    "band_fish.json": {
        "BandFishStartAtSettlement", "BandFishStartAtPlaying", "BandFishStartAtScoreDialog",
    },
    # Manual-grid solver owns its gated swipe sequence; it is not a tank router.
    "daily_magic_puzzle.json": {"DailyMagicPuzzleTask", "DailyMagicPuzzleSolve"},
    # Fish-baby configuration must finish before routing; the round action owns
    # toolbar state and resources, and exit nodes verify the actual page layers.
    "fish_baby.json": {
        "FishBabyTask", "FishBabyInit", "FishBabyUniformFood", "FishBabyUniformPlay",
        "FishBabyUniformMilk", "FishBabyHasTargets", "FishBabySkipAll",
        "FishBabySkipAllVerifyTank", "FishBabyStartRouter", "FishBabyIncubationCategory",
        "FishBabyIncubationSelected", "FishBabyIncubationFoodItems",
        "FishBabyIncubationPlayItems", "FishBabyIncubationMilkItems", "FishBabyRunRound",
        "FishBabyAtHome", "FishBabyHomeStart", "FishBabyVerifyIncubation",
        "FishBabyAtMainTank", "FishBabyEntryCoral", "FishBabyEntryBubble",
        "FishBabyEntryRouter", "FishBabyMainTankSky", "FishBabyRetryTank",
        "FishBabyExitIncubation", "FishBabyExitHome",
    } | {
        f"FishBaby{kind}{i}" for i in range(1, 9)
        for kind in ("FoodPreference", "Preference", "MilkPreference")
    },
    # Numbered-tank picker/retry gates lead back to the globally guarded router.
    "gold_shell_coupon.json": {
        "GoldShellCouponRetryEntryFromMainTank", "GoldShellCouponTank2ToPicker",
        "GoldShellCouponTank3ToPicker", "GoldShellCouponPickerTank1",
        "GoldShellCouponVerifyTank1BeforeEntry",
    },
    "golden_dolphin.json": {"GoldenDolphinResumeSettlement"},
    "shake_game.json": {"ShakeGameResumeSettlement"},
    # Daily completion/abort bridges do not navigate forward into another page.
    "green_wild.json": {"GreenWildVerifyTank", "GreenWildAbort"},
    # Deep-sea paid/free and return states have distinct local gates. Never apply
    # the generic activity-return control to a paid/free selection or result.
    "sea_dive.json": {
        "SeaDiveTask", "SeaDiveStartRouter", "SeaDiveStartAtHome", "SeaDiveStartAtPicker",
        "SeaDiveStartAtTank3", "SeaDiveStartAtTank1", "SeaDiveStartAtTank2",
        "SeaDiveVerifyTank3", "SeaDiveSubmarineEntry", "SeaDiveVerifyHome",
        "SeaDiveFreeStateRouter", "SeaDivePaidState", "SeaDiveFreeAvailable",
        "SeaDiveClickFreeButton", "SeaDiveDepthSelectPage", "SeaDiveChoose100m",
        "SeaDiveInGame", "SeaDiveClickInGameReturn", "SeaDiveResultPage",
        "SeaDiveClickResultReturn", "SeaDiveRetentionWait", "SeaDiveConfirmReturn",
        "SeaDiveVerifyHomeAfterCycle", "SeaDiveHomeClose", "SeaDiveVerifyExitTank3",
        "SeaDiveSelectTank1",
    },
    "secret_realm_gate.json": {"SecretRealmGateProcessOrder"},
    # Summon/fusion bridges reuse patrol gates; the intentional activity owns
    # its list/card/claim/exit stages instead of the accidental-popup handler.
    "daily_routine.json": {
        "DailyRoutineMagicSummonTank", "DailyRoutineGemFusionTank",
        "DailyRoutineMagicSummonDone", "DailyRoutineGemFusionDone",
        "DailyActivityEnergyAtTank", "DailyActivityEnergyEntry", "DailyActivityEnergyListPage",
        "DailyActivityEnergyCard1", "DailyActivityEnergyPage", "DailyActivityEnergyClaim",
        "DailyActivityEnergyClose", "DailyActivityEnergyListBack", "DailyActivityEnergyVerifyTank",
    },
}


def assert_global_popup_coverage(pipeline, locations):
    for filename, names in PAGE_LOCAL_CHAINS.items():
        for name in names:
            assert name in pipeline, f"stale popup exception: {name}"
            assert locations[name].name == filename, f"moved popup exception: {name}"
            assert pipeline[name].get("next"), f"obsolete popup exception: {name}"

    # The activity step must precede accidental activity handling, while the
    # other four popup types retain priority. Pin these exceptions, don't skip.
    ordered = {
        "DailyRoutineTask": GLOBAL_HANDLERS[1:] + ["DailyRoutineInitLog"],
        "DailyRoutineStepActivityEnergy": GLOBAL_HANDLERS[1:] + [
            "DailyActivityEnergyPage", "DailyActivityEnergyListPage", "DailyActivityEnergyAtTank",
        ],
    }
    for name, expected in ordered.items():
        assert pipeline[name]["next"] == expected, f"activity popup contract changed: {name}"
    assert pipeline["DailyRoutineDispatcher"]["next"][:6] == (
        GLOBAL_HANDLERS[1:] + ["DailyRoutineStepActivityEnergy", GLOBAL_HANDLERS[0]]
    ), "intentional activity must precede accidental activity handling"

    missing = []
    for name, node in pipeline.items():
        if locations[name].name in ISOLATED_PIPELINES:
            continue
        successors = node.get("next")
        if not successors or name in HANDLER_NODES | ATOMIC_NEXT_NODES | INTERNAL_CHAIN_NODES:
            continue
        if name in ordered or name == "DailyRoutineDispatcher":
            continue
        if name in PAGE_LOCAL_CHAINS.get(locations[name].name, set()):
            continue
        if successors[:len(GLOBAL_HANDLERS)] != GLOBAL_HANDLERS:
            missing.append(f"{locations[name]}::{name}")
    assert not missing, "global popup handlers are not first:\n" + "\n".join(missing)


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
    assert activity_page["recognition"] == "Or"
    assert activity_page["any_of"] == ["GlobalLuckyMomentTitle", "GlobalActivityPageReturn"]
    activity_return = pipeline["GlobalActivityPageReturn"]
    assert activity_return["template"] == "活动页面_退出.png"
    assert activity_return["roi"] == [0, 0, 136, 116]
    assert activity_return["action"] == "Click"
    assert "target" not in activity_return

    popup = pipeline["GlobalDailySignPopup"]
    assert popup["template"] == "签到_识别.png"
    assert popup["action"] == "DoNothing"
    assert popup["next"] == [
        "GlobalDailySignAlreadySigned", "GlobalDailySignClaim",
        "GlobalDailySignClaimByOcr", "GlobalDailySignAutoClosed",
    ]
    assert popup["timeout"] == 4000
    assert popup["on_error"] == ["GlobalDailySignFailed"]

    already_signed = pipeline["GlobalDailySignAlreadySigned"]
    assert already_signed["recognition"] == "OCR"
    assert already_signed["expected"] == "^已签到$"
    assert already_signed["action"] == "DoNothing"
    assert already_signed["roi"] == [0, 400, 1280, 320]
    assert already_signed["next"] == ["GlobalDailySignClose", "GlobalDailySignAutoClosed"]

    claim = pipeline["GlobalDailySignClaim"]
    assert claim["template"] == "签到_点击.png"
    assert claim["action"] == "Click"
    assert claim["roi"] == [0, 400, 1280, 320]
    assert "target" not in claim
    assert claim["next"] == ["GlobalDailySignClose", "GlobalDailySignAutoClosed"]
    assert claim["on_error"] == ["GlobalDailySignFailed"]

    claim_ocr = pipeline["GlobalDailySignClaimByOcr"]
    assert claim_ocr["recognition"] == "OCR"
    assert claim_ocr["expected"] == "^签到$"
    assert claim_ocr["roi"] == [0, 400, 1280, 320]
    assert claim_ocr["action"] == "Click"
    assert claim_ocr["next"] == ["GlobalDailySignClose", "GlobalDailySignAutoClosed"]
    assert claim_ocr["on_error"] == ["GlobalDailySignFailed"]

    close = pipeline["GlobalDailySignClose"]
    assert close["template"] == "签到_关闭.png"
    assert close["roi"] == [1000, 0, 220, 160]
    assert close["action"] == "Custom"
    assert close["custom_action"] == "DailySignCloseAction"
    assert close["custom_action_param"] == {"click_roi": [1084, 45, 41, 43]}
    assert close["on_error"] == ["GlobalDailySignFailed"]
    assert "target" not in close
    assert pipeline["GlobalDailySignFailed"]["action"] == "StopTask"

    auto_closed = pipeline["GlobalDailySignAutoClosed"]
    assert auto_closed["template"] == "签到_识别.png"
    assert auto_closed["inverse"] is True
    assert auto_closed["action"] == "DoNothing"

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

    if "--focused" not in sys.argv:
        assert_global_popup_coverage(pipeline, locations)
        # A lost prefix or an unreviewed node must still fail the full audit.
        broken = dict(pipeline)
        broken["FriendGemStartRouter"] = dict(pipeline["FriendGemStartRouter"], next=["FriendGemDone"])
        try:
            assert_global_popup_coverage(broken, locations)
        except AssertionError as error:
            assert "FriendGemStartRouter" in str(error)
        else:
            raise AssertionError("missing popup prefix was not detected")
        unknown = "UnreviewedPopupTransition"
        broken = dict(pipeline, **{unknown: {"next": ["FriendGemDone"]}})
        try:
            assert_global_popup_coverage(broken, dict(locations, **{unknown: locations["FishBabyTask"]}))
        except AssertionError as error:
            assert unknown in str(error)
        else:
            raise AssertionError("unreviewed local transition was not detected")

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


def test_close_action():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent import my_action
    from maa.define import Rect

    def run_case(states, *, missing_close=False, stopping=False, click_ok=True,
                 params='{"click_roi": [1084, 45, 41, 43]}', missing_title=False,
                 stop_after_click=False):
        clicks = []
        frames = iter(range(len(states)))
        def click(x, y):
            clicks.append((x, y))
            if stop_after_click:
                tasker.stopping = True
            return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=click_ok))

        controller = SimpleNamespace(post_click=click)
        tasker = SimpleNamespace(controller=controller, stopping=stopping, running=True)
        box = Rect(1083, 43, 48, 47)  # 本次真实 Maa 识别框，不假设它是 list。

        def recognize(name, frame):
            if name == "GlobalDailySignAutoClosed":
                # 真实 SDK 对 inverse 节点也返回取反前的 hit；旧实现会误报已消失。
                return SimpleNamespace(hit=not states[frame], box=Rect(521, 14, 234, 51))
            if name == "GlobalDailySignPopup":
                return None if missing_title else SimpleNamespace(hit=not states[frame])
            assert name == "GlobalDailySignClose"
            return SimpleNamespace(hit=not missing_close, box=box)

        context = SimpleNamespace(tasker=tasker, run_recognition=recognize)
        argv = SimpleNamespace(custom_action_param=params)
        with patch.object(my_action, "_capture_720p", side_effect=lambda _: next(frames)), \
                patch.object(my_action.time, "monotonic", side_effect=range(100)):
            result = my_action.DailySignCloseAction().run(context, argv)
        return result, clicks

    assert run_case([False, True]) == (True, [(1104, 66)])
    assert run_case([False, False, True]) == (True, [(1104, 66)] * 2)
    assert run_case([False] * 4) == (False, [(1104, 66)] * 3)
    assert run_case([True]) == (True, [])  # 自动关闭后不穿透点击。
    assert run_case([False], missing_close=True) == (False, [])
    assert run_case([False], stopping=True) == (False, [])
    assert run_case([False], click_ok=False) == (False, [(1104, 66)])
    assert run_case([False, True], params="null") == (True, [(1107, 66)])
    assert run_case([False], params='{"click_roi": [0, 0, 10, 10]}') == (False, [])
    assert run_case([False], params='{"click_roi": [0, 0, 0, 10]}') == (False, [])
    assert run_case([False], missing_title=True) == (False, [])
    assert run_case([False], stop_after_click=True) == (False, [(1104, 66)])
    print("[PASS] daily-sign close: center, retry, failure, auto-close and stop")


if __name__ == "__main__":
    run_tests()
    test_close_action()
