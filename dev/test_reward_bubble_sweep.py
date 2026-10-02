import json
from pathlib import Path


BOTTOM_ROI = (201, 630, 826, 66)
SWIPE_BEGIN = [221, 663]
SWIPE_END = [1007, 663]

CASES = [
    ("assets/resource/pipeline/collect_fish.json", "ClickFishBubble", "SweepFishTankBottomAfterBubble", "ResumeHarvest", 100),
    ("assets/resource/pipeline/features/patrol.json", "PatrolCollectTank1Bubble", "PatrolSweepTank1AfterBubble", "PatrolCollectTank1ImageWindow", 120),
    ("assets/resource/pipeline/features/patrol.json", "PatrolCollectTank2Bubble", "PatrolSweepTank2AfterBubble", "PatrolCollectTank2ImageWindow", 120),
    ("assets/resource/pipeline/features/patrol.json", "PatrolCollectTank3Bubble", "PatrolSweepTank3AfterBubble", "PatrolCollectTank3ImageWindow", 120),
]

EXEMPT_CLICKS = {
    ("assets/resource/pipeline/features/friend_gem.json", "FriendGemCollectBubble"),
}


def business_next(node):
    return [name for name in node.get("next", []) if not name.startswith("[JumpBack]")]


def point_in_roi(point):
    x, y = point
    left, top, width, height = BOTTOM_ROI
    return left <= x <= left + width and top <= y <= top + height


def main():
    loaded = {}
    covered_clicks = set()

    for path_str, click_name, sweep_name, return_name, post_delay in CASES:
        path = Path(path_str)
        pipeline = loaded.setdefault(path, json.loads(path.read_text(encoding="utf-8")))
        click = pipeline[click_name]
        sweep = pipeline[sweep_name]

        patrol = click_name.startswith("PatrolCollectTank")
        if patrol:
            assert click["recognition"] == "And" and click["box_index"] == 1
            assert pipeline[click["all_of"][1]]["template"] == "金币气泡.png"
            assert click["custom_action"] == "ClickRecognizedCenterAction"
        else:
            assert click["template"] == "金币气泡.png"
            assert click["action"] == "Click"
        assert click["post_delay"] == 0
        assert business_next(click) == [sweep_name]

        assert sweep["recognition"] == ("And" if patrol else "DirectHit")
        assert sweep["action"] == "Swipe"
        assert sweep["begin"] == SWIPE_BEGIN
        assert sweep["end"] == SWIPE_END
        assert sweep["begin"][0] < sweep["end"][0]
        assert point_in_roi(sweep["begin"]) and point_in_roi(sweep["end"])
        assert sweep["duration"] == 250
        assert sweep["post_delay"] == post_delay
        if patrol:
            reverse_name = sweep_name.replace("AfterBubble", "BackAfterBubble")
            assert business_next(sweep) == [reverse_name]
            reverse = pipeline[reverse_name]
            assert reverse["begin"] == SWIPE_END and reverse["end"] == SWIPE_BEGIN
            assert reverse["all_of"] == sweep["all_of"]
            assert business_next(reverse) == [return_name]
            assert "[JumpBack]PatrolShellPagePopup" in reverse["next"]
        else:
            reverse = pipeline["SweepFishTankBottomBackAfterBubble"]
            assert business_next(sweep) == ["SweepFishTankBottomBackAfterBubble"]
            assert reverse["begin"] == SWIPE_END and reverse["end"] == SWIPE_BEGIN
            assert business_next(reverse) == [return_name]
        covered_clicks.add((path.as_posix(), click_name))

    all_bubble_clicks = set()
    for path in Path("assets/resource/pipeline").rglob("*.json"):
        pipeline = json.loads(path.read_text(encoding="utf-8"))
        for name, node in pipeline.items():
            if node.get("template") == "金币气泡.png" and node.get("action") == "Click":
                all_bubble_clicks.add((path.as_posix(), name))
            if node.get("custom_action") == "ClickRecognizedCenterAction" and "PatrolCoinIdentity" in node.get("all_of", []):
                all_bubble_clicks.add((path.as_posix(), name))

    assert covered_clicks | EXEMPT_CLICKS == all_bubble_clicks

    friend_pipeline = json.loads(
        Path("assets/resource/pipeline/features/friend_gem.json").read_text(encoding="utf-8")
    )
    friend_click = friend_pipeline["FriendGemCollectBubble"]
    assert friend_click["post_delay"] == 500
    assert business_next(friend_click) == ["FriendGemRecordAttempt"]
    assert "FriendGemSweepBottomAfterBubble" not in friend_pipeline
    print("[PASS] 4 个产物气泡点击均衔接安全滑动，巡检滑动后使用专用模板恢复开贝壳页面")


if __name__ == "__main__":
    main()
