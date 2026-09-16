# -*- coding: utf-8 -*-
"""公主任务 Pipeline、ROI、模板和界面入口契约测试。"""
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "assets/resource/pipeline/features/princess_task.json"
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


def assert_fields(node, expected):
    assert {key: node.get(key) for key in expected} == expected


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def run_tests():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    assert business_next(pipeline["PrincessStartRouter"]) == [
        "PrincessPageReady",
        "PrincessOpenEntry",
    ]
    assert_fields(pipeline["PrincessOpenEntry"], {
        "recognition": "TemplateMatch",
        "template": "公主任务_入口.png",
        "roi": [29, 264, 50, 37],
        "action": "Click",
    })
    assert_fields(pipeline["PrincessPageReady"], {
        "recognition": "TemplateMatch",
        "template": "公主任务_识别.png",
        "roi": [512, 62, 253, 143],
        "action": "DoNothing",
    })
    assert business_next(pipeline["PrincessPageReady"]) == ["PrincessClaimRouter"]
    assert business_next(pipeline["PrincessClaimRouter"]) == [
        "PrincessClaimReward",
        "PrincessExit",
    ]

    claim = pipeline["PrincessClaimReward"]
    assert claim["recognition"] == "TemplateMatch"
    assert claim["template"] == "公主任务_领取奖励.png"
    assert claim["roi"] == [1028, 290, 62, 288]
    assert claim["action"] == "Click"
    assert "target" not in claim
    assert claim.get("max_hit") == 6
    assert business_next(claim) == ["PrincessClaimResultRouter"]

    assert business_next(pipeline["PrincessClaimResultRouter"]) == [
        "PrincessClaimSuccess",
        "PrincessClaimFailure",
    ]
    success = pipeline["PrincessClaimSuccess"]
    assert success["recognition"] == "OCR"
    assert success["expected"] == "^开心收下$"
    assert success["roi"] == [586, 518, 102, 32]
    assert success["action"] == "Click"
    assert "target" not in success
    assert business_next(success) == ["PrincessPageAfterClaim"]

    failure = pipeline["PrincessClaimFailure"]
    assert failure["template"] == "公主任务_领取失败.png"
    assert failure["action"] == "Click"
    assert "target" not in failure
    assert business_next(pipeline["PrincessPageAfterClaim"]) == ["PrincessClaimRouter"]

    for gone in (
        "PrincessClaimBottom",
        "PrincessClaimMiddle",
        "PrincessClaimTop",
        "PrincessBottomRouter",
        "PrincessMiddleRouter",
        "PrincessTopRouter",
    ):
        assert gone not in pipeline

    exit_node = pipeline["PrincessExit"]
    assert exit_node["template"] == "公主任务_退出.png"
    assert exit_node["roi"] == [1068, 121, 37, 39]
    assert exit_node["action"] == "Click"
    assert "target" not in exit_node
    assert pipeline["PrincessVerifyTank"]["template"] == "主界面特征.png"
    assert pipeline["PrincessAbort"]["action"] == "StopTask"

    for node in pipeline.values():
        successors = node.get("next")
        if successors:
            assert successors[:len(GLOBAL_HANDLERS)] == GLOBAL_HANDLERS

    for name in (
        "公主任务_入口.png",
        "公主任务_识别.png",
        "公主任务_领取奖励.png",
        "公主任务_领取失败.png",
        "公主任务_退出.png",
    ):
        assert (IMAGE_DIR / name).is_file(), f"missing template: {name}"

    for node in pipeline.values():
        template_name = node.get("template", "")
        if template_name.startswith("公主任务_"):
            template_width, template_height = png_size(IMAGE_DIR / template_name)
            _, _, roi_width, roi_height = node["roi"]
            assert template_width <= roi_width and template_height <= roi_height, (
                f"{template_name} {template_width}x{template_height} exceeds ROI "
                f"{roi_width}x{roi_height}"
            )

    interface_paths = [
        ROOT / "assets/interface.json",
        ROOT / "client/interface.json",
        ROOT / "client_avalonia/interface.json",
    ]
    interface_bytes = [path.read_bytes() for path in interface_paths]
    assert interface_bytes[0] == interface_bytes[1] == interface_bytes[2]
    interface = json.loads(interface_bytes[0].decode("utf-8"))
    princess_tasks = [task for task in interface["task"] if task["entry"] == "PrincessTask"]
    assert len(princess_tasks) == 1
    assert princess_tasks[0]["name"] == "公主任务"
    assert princess_tasks[0]["default_check"] is False

    print("[PASS] PrincessTask column-claim topology, ROI, assets, and interface contract")


if __name__ == "__main__":
    run_tests()
