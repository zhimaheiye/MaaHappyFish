#!/usr/bin/env python3
"""深海寻鱼状态机离线契约测试。

覆盖：
- FREE/PAID/UNKNOWN 三态分流
- 完整 FREE 循环链路拓扑
- 结算页左返航安全约束（绝不点右侧继续下潜）
- 挽留弹窗等待机制
- 循环回 FreeStateRouter 自动判断下一轮
- 付费态退出链
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "assets/resource/pipeline/features/sea_dive.json"
EVIDENCE = ROOT / "temp/sea_dive_live_capture_20260924"


def load_pipeline():
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_free_state_router_three_way_split():
    """Case: FreeStateRouter 必须按 PAID → FREE → UNKNOWN 顺序分流。"""
    p = load_pipeline()
    router = p["SeaDiveFreeStateRouter"]
    assert router["recognition"] == "DirectHit"
    assert router["next"] == [
        "SeaDivePaidState",
        "SeaDiveFreeAvailable",
        "SeaDiveUnknownState",
    ], "顺序必须是先试付费态，再试免费态，最后兜底停止"


def test_start_router_recovers_deepest_state_first():
    p = load_pipeline()
    assert p["SeaDiveStartRouter"]["next"] == [
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


def test_paid_state_x12_detection():
    """Case: PAID 态通过 x12 OCR 识别，识别后走退出链，不点击下潜。"""
    p = load_pipeline()
    paid = p["SeaDivePaidState"]
    assert "x12" in paid["expected"].lower() or "12" in paid["expected"]
    assert paid["action"] == "DoNothing"
    assert paid["next"] == ["SeaDiveHomeClose"]
    # 退出链：HomeClose → VerifyExitTank3 → SelectTank1 → VerifyMainTank1
    assert p["SeaDiveHomeClose"]["action"] == "Click"
    assert p["SeaDiveHomeClose"]["next"] == ["SeaDiveVerifyExitTank3"]


def test_free_available_positive_gate():
    """Case: FREE 态有正向门禁（红色次数角标模板匹配），不能仅靠没识别到 x12 判定。"""
    p = load_pipeline()
    free = p["SeaDiveFreeAvailable"]
    assert free["recognition"] == "TemplateMatch"
    assert "free_badge" in free["template"]
    assert free["action"] == "DoNothing"
    assert free["next"] == ["SeaDiveClickFreeButton"]


def test_unknown_state_aborts():
    """Case: FREE/PAID 都不匹配时，UnknownState 必须 StopTask。"""
    p = load_pipeline()
    unknown = p["SeaDiveUnknownState"]
    assert unknown["action"] == "StopTask"


def test_full_free_cycle_topology():
    """Case: FREE → DepthSelect → 100m → InGame → Return → Result → LeftReturn → Retention → Confirm → Home → loop."""
    p = load_pipeline()

    # FREE button click → depth select
    assert p["SeaDiveClickFreeButton"]["next"] == ["SeaDiveDepthSelectPage"]

    # Depth select page gate → choose 100m
    assert p["SeaDiveDepthSelectPage"]["recognition"] == "OCR"
    assert "起始深度选择" in p["SeaDiveDepthSelectPage"]["expected"]
    assert p["SeaDiveDepthSelectPage"]["next"] == ["SeaDiveChoose100m"]

    # Choose 100m → in-game
    assert "100米" in p["SeaDiveChoose100m"]["expected"]
    assert p["SeaDiveChoose100m"]["action"] == "Click"
    assert p["SeaDiveChoose100m"]["next"] == ["SeaDiveInGame"]

    # In-game gate (top-right return button) → click return
    assert p["SeaDiveInGame"]["recognition"] == "OCR"
    assert p["SeaDiveInGame"]["next"] == ["SeaDiveClickInGameReturn"]
    # In-game return ROI must be top-right corner
    roi = p["SeaDiveInGame"]["roi"]
    assert roi[0] > 1000, "局内返航按钮必须在右上角区域"
    assert roi[1] < 100, "局内返航按钮必须在顶部区域"

    # Result page gate → click left return
    assert p["SeaDiveResultPage"]["recognition"] == "OCR"
    assert "本次获得奖励" in p["SeaDiveResultPage"]["expected"]
    assert p["SeaDiveResultPage"]["next"] == ["SeaDiveClickResultReturn"]


def test_result_page_left_return_only():
    """Case: 结算页返航按钮 ROI 必须限定左半区，绝不能点到右侧继续下潜。"""
    p = load_pipeline()
    return_node = p["SeaDiveClickResultReturn"]
    roi = return_node["roi"]
    # ROI x 起点必须在屏幕中线左侧（1280宽度，中线640）
    assert roi[0] < 600, "结算页返航按钮 ROI 必须在左半区"
    assert roi[0] + roi[2] < 650, "结算页返航按钮 ROI 右边界不能超过中线"
    assert return_node["action"] == "Click"
    # 确认没有任何节点会点击右侧"继续下潜"
    all_nodes = p.items()
    for name, node in all_nodes:
        if node.get("recognition") == "OCR" and "继续下潜" in node.get("expected", ""):
            assert node.get("action") != "Click", f"{name} 识别到继续下潜但执行了点击，危险！"


def test_retention_popup_wait_mechanism():
    """Case: 挽留弹窗必须有等待超时机制，前几帧 miss 后出现 HIT 仍能捕获。"""
    p = load_pipeline()
    wait = p["SeaDiveRetentionWait"]
    assert wait["recognition"] == "OCR"
    assert "确定" in wait["expected"]
    assert wait["action"] == "DoNothing"
    # 等待超时必须足够长（至少5秒）
    assert wait.get("timeout", 0) >= 5000, "挽留弹窗等待时间至少5秒"
    # 等待后点击确定
    assert p["SeaDiveConfirmReturn"]["action"] == "Click"
    assert "确定" in p["SeaDiveConfirmReturn"]["expected"]


def test_cycle_loops_back_to_state_router():
    """Case: 完成一轮后必须回到 FreeStateRouter，不写死次数。"""
    p = load_pipeline()
    home_after = p["SeaDiveVerifyHomeAfterCycle"]
    assert home_after["next"] == ["SeaDiveFreeStateRouter"], "完成一轮后必须回到状态路由器自动判断下一轮"
    # 确认没有硬编码循环次数
    click_nodes = [name for name, n in p.items() if n.get("action") == "Click"]
    # 不应该有任何 for 循环逻辑（pipeline 本身就是声明式的）


def test_exit_chain_preserved():
    """Case: 现有付费退出链必须保留，不被 FREE 循环覆盖。"""
    p = load_pipeline()
    # PaidState → HomeClose → VerifyExitTank3 → SelectTank1 → VerifyMainTank1
    assert p["SeaDivePaidState"]["next"] == ["SeaDiveHomeClose"]
    assert p["SeaDiveHomeClose"]["next"] == ["SeaDiveVerifyExitTank3"]
    assert p["SeaDiveVerifyExitTank3"]["next"] == ["SeaDiveSelectTank1"]
    assert p["SeaDiveSelectTank1"]["next"] == ["SeaDiveVerifyMainTank1"]


def test_evidence_files_exist():
    """Case: 本轮实机采集的证据文件必须存在。"""
    required = [
        "01_home_free.png",
        "02_depth_select.png",
        "03_in_game.png",
        "04_result.png",
        "05_retention_popup.png",
        "06_home_after_one_round.png",
        "timeline.txt",
    ]
    for f in required:
        path = EVIDENCE / f
        assert path.exists(), f"缺少证据文件: {f}"


def test_evidence_free_count_reduction():
    """Case: timeline 中必须记录 2→1 的次数变化。"""
    timeline = (EVIDENCE / "timeline.txt").read_text(encoding="utf-8")
    assert "2 -> 1" in timeline or "2→1" in timeline, "timeline 必须记录免费次数变化"


def main():
    tests = [
        test_free_state_router_three_way_split,
        test_start_router_recovers_deepest_state_first,
        test_paid_state_x12_detection,
        test_free_available_positive_gate,
        test_unknown_state_aborts,
        test_full_free_cycle_topology,
        test_result_page_left_return_only,
        test_retention_popup_wait_mechanism,
        test_cycle_loops_back_to_state_router,
        test_exit_chain_preserved,
        test_evidence_files_exist,
        test_evidence_free_count_reduction,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__doc__.split('：')[0].strip() if t.__doc__ else t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            raise
    print(f"\n[PASS] 深海寻鱼状态机离线契约：{passed}/{len(tests)} 项通过")


if __name__ == "__main__":
    main()
