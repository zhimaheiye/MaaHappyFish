import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "assets/resource/pipeline/features/gem_order.json"
GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
]


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


def run_tests():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    assert business_next(pipeline["GemOrderTask"]) == [
        "GemOrderOnPage",
        "GemOrderOpenEntry",
        "GemOrderAbort",
    ]

    expected_templates = {
        "GemOrderOpenEntry": ("宝石订单_入口.png", [30, 377, 52, 48]),
        "GemOrderOnPage": ("宝石订单_识别.png", [535, 1, 316, 155]),
        "GemOrderSpecialCompletable": (
            "宝石订单_特殊订单_可完成.png",
            [241, 199, 150, 120],
        ),
        "GemOrderNormalCompletable": (
            "宝石订单_普通订单_可完成.png",
            [241, 199, 150, 120],
        ),
        "GemOrderExit": ("宝石订单_退出.png", [1107, 84, 37, 36]),
    }
    for node_name, (template, roi) in expected_templates.items():
        node = pipeline[node_name]
        assert node["template"] == template
        assert node["roi"] == roi
        assert (ROOT / "assets/resource/image" / template).is_file()

    router = business_next(pipeline["GemOrderRouter"])
    assert router == [
        "GemOrderAllIssued",
        "GemOrderSpecialCompletable",
        "GemOrderNormalCompletable",
        "GemOrderDiscard",
        "GemOrderAbort",
    ]
    assert pipeline["GemOrderAllIssued"]["expected"] == "10/10"
    assert pipeline["GemOrderAllIssued"]["roi"] == [288, 86, 172, 140]

    for node_name in ("GemOrderSpecialCompletable", "GemOrderNormalCompletable"):
        assert business_next(pipeline[node_name]) == ["GemOrderComplete"]
        assert pipeline[node_name]["action"] == "DoNothing"

    complete = pipeline["GemOrderComplete"]
    assert complete["recognition"] == "OCR"
    assert complete["expected"] == "^完成$"
    assert complete["roi"] == [944, 625, 65, 33]
    assert complete["action"] == "Click"
    assert "target" not in complete
    assert business_next(complete) == ["GemOrderOnPage"]

    discard = pipeline["GemOrderDiscard"]
    assert discard["recognition"] == "OCR"
    assert discard["expected"] == "^[丢丟]弃$"
    assert discard["roi"] == [735, 626, 66, 32]
    assert discard["action"] == "Click"
    assert "target" not in discard
    assert business_next(discard) == ["GemOrderConfirmDiscard"]

    confirm_discard = pipeline["GemOrderConfirmDiscard"]
    assert confirm_discard["recognition"] == "OCR"
    assert confirm_discard["expected"] == "^[丢丟]弃$"
    assert confirm_discard["roi"] == [603, 460, 85, 32]
    assert confirm_discard["action"] == "Click"
    assert "target" not in confirm_discard
    assert business_next(confirm_discard) == ["GemOrderOnPage"]

    assert business_next(pipeline["GemOrderAllIssued"]) == ["GemOrderExit"]
    assert business_next(pipeline["GemOrderExit"]) == ["GemOrderVerifyTank"]
    assert pipeline["GemOrderVerifyTank"]["template"] == "主界面特征.png"
    assert pipeline["GemOrderAbort"]["action"] == "StopTask"

    interface_paths = [
        ROOT / "assets/interface.json",
        ROOT / "client/interface.json",
        ROOT / "client_avalonia/interface.json",
    ]
    raw = [path.read_bytes() for path in interface_paths]
    assert raw[0] == raw[1] == raw[2]
    interface = json.loads(raw[0].decode("utf-8"))
    task = next(task for task in interface["task"] if task["entry"] == "GemOrderTask")
    assert task["name"] == "宝石订单"
    assert task["default_check"] is False

    print("[PASS] 宝石订单双对号分流、双重丢弃确认、10/10 终态与退出契约")


if __name__ == "__main__":
    run_tests()
