import json
from pathlib import Path


PIPELINE_DIR = Path("assets/resource/pipeline")
GLOBAL_HANDLERS = [
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
]
HANDLER_NODES = {
    "GlobalDailySignPopup",
    "GlobalDailySignClaim",
    "GlobalSpecialOfferPopup",
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

    popup = pipeline["GlobalDailySignPopup"]
    assert popup["template"] == "签到_识别.png"
    assert popup["action"] == "DoNothing"
    assert popup["next"] == ["GlobalDailySignClaim"]

    claim = pipeline["GlobalDailySignClaim"]
    assert claim["template"] == "签到_点击.png"
    assert claim["action"] == "Click"
    assert "target" not in claim
    assert claim["next"] == ["GlobalDailySignClose", "GlobalDailySignAutoClosed"]

    close = pipeline["GlobalDailySignClose"]
    assert close["template"] == "签到_关闭.png"
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

    missing = []
    for name, node in pipeline.items():
        successors = node.get("next")
        if name in HANDLER_NODES or not successors:
            continue
        if successors[:2] != GLOBAL_HANDLERS:
            missing.append(f"{locations[name]}::{name}")
    assert not missing, "global popup handlers are not first:\n" + "\n".join(missing)

    image_dir = Path("assets/resource/image")
    for template in (
        "签到_识别.png",
        "签到_点击.png",
        "签到_关闭.png",
        "特惠礼包_识别.png",
        "特惠礼包_关闭.png",
    ):
        assert (image_dir / template).is_file(), f"missing template: {template}"

    print("[PASS] global daily-sign and special-offer popup handlers")


if __name__ == "__main__":
    run_tests()
