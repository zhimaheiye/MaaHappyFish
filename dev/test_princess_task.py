# -*- coding: utf-8 -*-
"""公主任务 Pipeline、ROI、模板和界面入口契约测试。"""
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.my_action import ResetPrincessClaimHitsAction


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

    entry = pipeline["PrincessTask"]
    assert entry["action"] == "Custom"
    assert entry["custom_action"] == "ResetPrincessClaimHitsAction"

    class HitContext:
        def __init__(self, failed_name=None):
            self.cleared = []
            self.failed_name = failed_name

        def clear_hit_count(self, name):
            self.cleared.append(name)
            return name != self.failed_name

    claim_names = ["PrincessClaimTop", "PrincessClaimMiddle", "PrincessClaimBottom"]
    context = HitContext()
    action = ResetPrincessClaimHitsAction()
    argv = SimpleNamespace(custom_action_param="null")
    assert action.run(context, argv) is True
    assert action.run(context, argv) is True  # 同一轮日常收尾的末尾再次进入
    assert context.cleared == claim_names * 2
    assert action.run(HitContext(failed_name="PrincessClaimMiddle"), argv) is False

    assert business_next(pipeline["PrincessStartRouter"]) == [
        "PrincessTreasureClaimSuccess",
        "PrincessClaimSuccess",
        "PrincessClaimFailure",
        "PrincessTreasureTaskPage",
        "PrincessPageReady",
        "PrincessBountyDeliver",
        "PrincessDiaryTab",
        "PrincessBountyTab",
        "PrincessOpenEntry",
    ]
    assert_fields(pipeline["PrincessOpenEntry"], {
        "recognition": "TemplateMatch",
        "template": "公主任务_入口.png",
        "roi": [29, 264, 50, 37],
        "action": "Click",
    })
    assert business_next(pipeline["PrincessOpenEntry"]) == [
        "PrincessTreasureTaskPage",
        "PrincessPageReady",
        "PrincessBountyDeliver",
        "PrincessDiaryTab",
        "PrincessBountyTab",
    ]
    diary_tab = pipeline["PrincessDiaryTab"]
    assert_fields(diary_tab, {
        "recognition": "OCR",
        "expected": "日记",
        "roi": [512, 62, 253, 143],
        "action": "DoNothing",
    })
    bounty_tab = pipeline["PrincessBountyTab"]
    assert_fields(bounty_tab, {
        "recognition": "OCR",
        "expected": "悬赏|赏金",
        "roi": [512, 62, 253, 143],
        "action": "DoNothing",
    })
    assert business_next(bounty_tab) == ["PrincessBountyDeliver"]
    deliver = pipeline["PrincessBountyDeliver"]
    assert_fields(deliver, {
        "recognition": "OCR",
        "expected": "^交付任务$",
        "roi": [260, 250, 720, 430],
        "action": "Click",
    })
    assert "target" not in deliver
    assert deliver.get("max_hit") == 1
    assert business_next(deliver) == ["PrincessExit"]
    assert_fields(pipeline["PrincessPageReady"], {
        "recognition": "TemplateMatch",
        "template": "公主任务_识别.png",
        "roi": [512, 62, 253, 143],
        "action": "DoNothing",
    })
    page_ready_next = [
        "PrincessClaimTop",
        "PrincessClaimMiddle",
        "PrincessClaimBottom",
        "PrincessTreasureTaskPage",
        "PrincessExit",
    ]
    assert business_next(pipeline["PrincessPageReady"]) == page_ready_next
    assert business_next(diary_tab) == page_ready_next
    assert "PrincessBountyDeliver" not in business_next(pipeline["PrincessPageReady"])
    assert "PrincessBountyDeliver" not in business_next(diary_tab)
    for router_name in ("PrincessStartRouter", "PrincessOpenEntry"):
        route = business_next(pipeline[router_name])
        assert route.index("PrincessPageReady") < route.index("PrincessBountyDeliver") < route.index("PrincessDiaryTab")
    claim_slots = [
        ("PrincessClaimTop", [1028, 290, 62, 96]),
        ("PrincessClaimMiddle", [1028, 386, 62, 96]),
        ("PrincessClaimBottom", [1028, 482, 62, 96]),
    ]
    for node_name, roi in claim_slots:
        claim = pipeline[node_name]
        assert claim["recognition"] == "TemplateMatch"
        assert claim["template"] == "公主任务_领取奖励.png"
        assert claim["roi"] == roi
        assert claim["action"] == "Click"
        assert "target" not in claim
        assert claim.get("max_hit") == 1
        assert business_next(claim) == ["PrincessClaimResultRouter"]

    assert business_next(pipeline["PrincessClaimResultRouter"]) == [
        "PrincessClaimSuccess",
        "PrincessClaimFailure",
        "PrincessClaimNeedMorePoints",
    ]
    need_more = pipeline["PrincessClaimNeedMorePoints"]
    assert need_more["recognition"] == "OCR"
    assert need_more["expected"] == "积分不足|无法领取"
    assert business_next(need_more) == ["PrincessClaimFailure"]
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
    assert business_next(pipeline["PrincessPageAfterClaim"]) == page_ready_next
    assert "PrincessBountyDeliver" not in business_next(pipeline["PrincessPageAfterClaim"])
    assert pipeline["PrincessPageAfterClaim"]["on_error"] == [
        "PrincessTreasureTaskPage"
    ]
    assert pipeline["PrincessClaimFailure"]["roi"] == [760, 380, 180, 180]

    treasure_page = pipeline["PrincessTreasureTaskPage"]
    assert_fields(treasure_page, {
        "recognition": "OCR",
        "expected": "公主宝箱任务",
        "roi": [494, 158, 292, 141],
        "action": "DoNothing",
    })
    assert business_next(treasure_page) == [
        "PrincessTreasureClaimAvailable",
        "PrincessExit",
    ]
    assert treasure_page["on_error"] == ["PrincessExit"]

    treasure_claim = pipeline["PrincessTreasureClaimAvailable"]
    assert_fields(treasure_claim, {
        "recognition": "TemplateMatch",
        "template": "公主宝箱任务_领取.png",
        "roi": [376, 501, 40, 40],
        "action": "Click",
    })
    assert "target" not in treasure_claim
    assert business_next(treasure_claim) == ["PrincessTreasureClaimSuccess"]

    treasure_success = pipeline["PrincessTreasureClaimSuccess"]
    assert_fields(treasure_success, {
        "recognition": "OCR",
        "expected": "^你真棒$",
        "roi": [596, 517, 86, 31],
        "action": "Click",
    })
    assert "target" not in treasure_success
    assert business_next(treasure_success) == ["PrincessExit"]

    for gone in (
        "PrincessClaimReward",
        "PrincessClaimRouter",
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
    assert pipeline["PrincessAbort"]["action"] == "DoNothing"

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
        "公主宝箱任务_领取.png",
    ):
        assert (IMAGE_DIR / name).is_file(), f"missing template: {name}"

    for node in pipeline.values():
        template_name = node.get("template", "")
        if template_name.startswith(("公主任务_", "公主宝箱任务_")):
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

    print("[PASS] PrincessTask per-entry hit reset, three-slot topology, ROI, assets, and interface contract")


if __name__ == "__main__":
    run_tests()
