# -*- coding: utf-8 -*-
"""
日常收尾 (DailyRoutineTask) 串行容器多任务组合调度测试
验证:
1. 组合1: 五个全部勾选 (BAND_FISH_PASS1 -> FREE_GIFT -> GOLDEN_DOLPHIN -> FISHING -> ROMANTIC_HOUSE -> BAND_FISH_PASS2 -> ALL_DONE)
2. 组合2: 只勾选浪漫满屋 (ROMANTIC_HOUSE -> ALL_DONE)
3. 组合3: 只勾选金海豚 (GOLDEN_DOLPHIN -> ALL_DONE)
4. 组合4: 浪漫满屋 + 钓鱼达人 (FISHING -> ROMANTIC_HOUSE -> ALL_DONE)
5. 组合5: 全部未勾选 (ALL_DONE)
6. 管道拓扑完整性校验: DailyRoutineDispatcher / Step / Enable 节点
7. 独立运行兼容性: daily_routine_state["active"] 为 False 时的安全保障
"""
import json
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.runtime_state import daily_routine_state
from agent.my_action import (
    InitDailyRoutineAction,
    advance_daily_routine_step,
    DailyFreeGiftDoneAction,
    ReindeerFishDoneAction,
    DailyRoutineFinishAction,
    RomanticHouseExitToTankAction,
)
from agent.my_reco import (
    CheckDailyRoutineStepReco,
    CheckBandFishDailyRoutineReco,
    CheckBandFishStandalonePendingReco,
    CheckBandFishStandaloneDoneReco,
)

GLOBAL_POPUP_HANDLERS = {
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_POPUP_HANDLERS]


class MockArg:
    def __init__(self, param):
        self.custom_action_param = json.dumps(param) if isinstance(param, dict) else param
        self.custom_recognition_param = self.custom_action_param


class MockContext:
    def __init__(self, pipeline_data=None):
        self.pipeline_data = pipeline_data or {}

    def get_node_data(self, name):
        return self.pipeline_data.get(name)


def test_pipeline_topology():
    print("--- [Check 1: Pipeline 拓扑与路由检查] ---")
    pfiles = glob.glob(os.path.join("assets", "resource", "pipeline", "**", "*.json"), recursive=True)
    pdata = {}
    for pf in pfiles:
        with open(pf, "r", encoding="utf-8") as f:
            pdata.update(json.load(f))

    # 1. 验证 6 个 Enable 节点存在
    for en in [
        "DailyRoutineEnableFreeGift",
        "DailyRoutineEnableReindeerFish",
        "DailyRoutineEnableBandFish",
        "DailyRoutineEnableGoldenDolphin",
        "DailyRoutineEnableFishing",
        "DailyRoutineEnableRomanticHouse",
    ]:
        assert en in pdata, f"Missing enable node: {en}"
        assert pdata[en].get("enabled") is False, f"{en} default should be enabled: false"
    print("[PASS] 6 个 DailyRoutineEnable* 节点配置正确 (默认 enabled: false)")

    # 2. 验证 Dispatcher 候选
    disp = pdata.get("DailyRoutineDispatcher", {})
    candidates = business_next(disp)
    expected_order = [
        "DailyRoutineStepFreeGift",
        "DailyRoutineStepReindeerFish",
        "DailyRoutineStepBandFishPass1",
        "DailyRoutineStepGoldenDolphin",
        "DailyRoutineStepFishing",
        "DailyRoutineStepRomanticHouse",
        "DailyRoutineStepBandFishPass2",
        "DailyRoutineStepAllDone",
    ]
    assert candidates == expected_order, f"Dispatcher candidates mismatch: {candidates} vs {expected_order}"
    print("[PASS] DailyRoutineDispatcher 候选节点顺序与保留项完全匹配")

    # 3. 验证 RomanticHouseDone 接入
    rh_done = pdata.get("RomanticHouseDone", {})
    assert rh_done.get("action") == "Custom"
    assert rh_done.get("custom_action") == "RomanticHouseExitToTankAction"
    assert business_next(rh_done) == ["DailyRoutineDispatcher"]
    print("[PASS] RomanticHouseDone 正确配置为 RomanticHouseExitToTankAction 并接入 Dispatcher")

    # 4. 免费礼包必须是二选一分支；领取成功后不再检查“已售罄”。
    assert business_next(pdata["DailyFreeGiftAvailabilityRouter"]) == [
        "DailyFreeGiftAlreadySoldOut",
        "DailyFreeGiftClaimable",
    ]
    # 实机日志中标题可能被 OCR 成“售罄”或“已售罄”；短语匹配必须兼容两者，
    # 否则灰色禁用按钮仍会被识别成“免费领取”，导致误入领取分支。
    assert pdata["DailyFreeGiftAlreadySoldOut"]["expected"] == "售罄"
    assert business_next(pdata["DailyFreeGiftClaimable"]) == ["DailyFreeGiftRewardReturn"]
    assert business_next(pdata["DailyFreeGiftRewardReturn"]) == ["DailyFreeGiftExitRecharge"]
    assert business_next(pdata["DailyFreeGiftAlreadySoldOut"]) == ["DailyFreeGiftExitRecharge"]
    assert pdata["DailyFreeGiftTankEntry"]["roi"] == [455, 0, 140, 115]
    assert "target" not in pdata["DailyFreeGiftTankEntry"]
    assert business_next(pdata["DailyFreeGiftVerifyTank"]) == ["DailyRoutineDispatcher"]
    print("[PASS] 免费领取/已售罄分支独立，并在识别返回鱼缸后汇合")

    # 5. 乐队鱼退出后必须按运行模式分流，独立任务不能跌入未激活的日常调度器。
    assert business_next(pdata["BandFishDone"]) == ["BandFishAfterExitRouter"]
    assert business_next(pdata["BandFishAfterExitRouter"]) == [
        "BandFishAfterExitDailyRoutine",
        "BandFishAfterExitStandalonePending",
        "BandFishAfterExitStandaloneDone",
    ]
    assert business_next(pdata["BandFishAfterExitDailyRoutine"]) == ["DailyRoutineDispatcher"]
    assert business_next(pdata["BandFishAfterExitStandalonePending"]) == ["BandFishStartRouter"]
    assert "next" not in pdata["BandFishAfterExitStandaloneDone"]
    print("[PASS] 乐队鱼退出后的日常/独立回访/独立完成三路分流正确")

    # 6. 独立钓鱼与日常收尾必须复用同一个钓场选项，并保持三份配置同步。
    interface_paths = [
        os.path.join("assets", "interface.json"),
        os.path.join("client", "interface.json"),
        os.path.join("client_avalonia", "interface.json"),
    ]
    raw_interfaces = [open(path, "rb").read() for path in interface_paths]
    assert raw_interfaces[0] == raw_interfaces[1] == raw_interfaces[2]
    interface = json.loads(raw_interfaces[0].decode("utf-8"))
    tasks = {task["entry"]: task for task in interface["task"]}
    assert "钓鱼地点" in tasks["FishingTask"]["option"]
    assert "钓鱼地点" in tasks["DailyRoutineTask"]["option"]
    routine_cases = {
        case["name"] for case in interface["option"]["日常收尾任务"]["cases"]
    }
    assert "驯鹿鱼送收礼物" in routine_cases
    print("[PASS] 独立钓鱼与日常收尾共享钓鱼地点选项，三份 interface.json 同步")

    # 7. 驯鹿鱼已知分支必须全部基于识别结果点击，并使用统一返回 OCR 范围。
    assert business_next(pdata["ReindeerFishStartRouter"]) == [
        "ReindeerFishRewardReturn",
        "ReindeerFishCollectAll",
        "ReindeerFishReplyAll",
        "ReindeerFishDirectGift",
        "ReindeerFishStartAtGrid",
        "ReindeerFishStartAtTank",
    ]
    # 实机 OCR 曾把“一键收取”稳定识别为“键收取”；使用共同稳定子串兼容两者。
    assert pdata["ReindeerFishCollectAll"]["expected"] == "键收取"
    assert pdata["ReindeerFishCollectAll"]["roi"] == [678, 562, 235, 147]
    assert pdata["ReindeerFishReplyAll"]["expected"] == "一键回礼"
    assert pdata["ReindeerFishReplyAll"]["roi"] == [480, 562, 232, 143]
    assert pdata["ReindeerFishDirectGift"]["expected"] == "直接赠送"
    assert "roi" not in pdata["ReindeerFishDirectGift"]
    assert pdata["ReindeerFishCommonBack"]["expected"] == "返回"
    assert pdata["ReindeerFishCommonBack"]["roi"] == [1, 0, 189, 119]
    for node_name in (
        "ReindeerFishCollectAll",
        "ReindeerFishReplyAll",
        "ReindeerFishDirectGift",
        "ReindeerFishRewardReturn",
        "ReindeerFishCommonBack",
    ):
        assert pdata[node_name]["action"] == "Click"
        assert "target" not in pdata[node_name]
    print("[PASS] 驯鹿鱼收取/回礼/直接赠送分支与通用返回均为识别点击，无坐标兜底")


def simulate_flow(config_param):
    """模拟一条完整的调度流转"""
    init_action = InitDailyRoutineAction()
    ctx = MockContext()
    arg = MockArg(config_param)

    # 1. 初始化
    init_action.run(ctx, arg)
    visited_steps = []
    step_reco = CheckDailyRoutineStepReco()

    # 循环调度直至 ALL_DONE
    max_loops = 10
    loops = 0
    step_mapping = {
        "BAND_FISH_PASS1": ("BandFish", "PENDING"),
        "REINDEER_FISH": ("ReindeerFish", "DONE"),
        "GOLDEN_DOLPHIN": ("GoldenDolphin", "DONE"),
        "FISHING": ("Fishing", "DONE"),
        "ROMANTIC_HOUSE": ("RomanticHouse", "DONE"),
        "BAND_FISH_PASS2": ("BandFish", "DONE"),
    }

    while loops < max_loops:
        cur_step = daily_routine_state["step"]
        visited_steps.append(cur_step)

        # 校验识别器能否命中当前 step
        hit = step_reco.analyze(ctx, MockArg({"expected_step": cur_step}))
        assert hit is not None, f"Reco failed to match step: {cur_step}"

        if cur_step == "ALL_DONE":
            finish_action = DailyRoutineFinishAction()
            finish_action.run(ctx, arg)
            break

        if cur_step == "FREE_GIFT":
            assert DailyFreeGiftDoneAction().run(ctx, arg) is True
            loops += 1
            continue

        if cur_step == "REINDEER_FISH":
            assert ReindeerFishDoneAction().run(ctx, arg) is True
            loops += 1
            continue

        task_name, biz_st = step_mapping[cur_step]
        advance_daily_routine_step(task_name, biz_st)
        loops += 1

    assert daily_routine_state["active"] is False, "Active flag should be reset to False after finish"
    return visited_steps


def test_combination_1():
    print("--- [Check 2: 组合 1 - 全部勾选] ---")
    config = {"free_gift": True, "reindeer_fish": True, "band_fish": True, "golden_dolphin": True, "fishing": True, "romantic_house": True}
    steps = simulate_flow(config)
    expected = ["BAND_FISH_PASS1", "FREE_GIFT", "REINDEER_FISH", "GOLDEN_DOLPHIN", "FISHING", "ROMANTIC_HOUSE", "BAND_FISH_PASS2", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 组合 1 完整顺序验证通过: {' -> '.join(steps)}")


def test_combination_2():
    print("--- [Check 3: 组合 2 - 仅浪漫满屋] ---")
    config = {"romantic_house": True}
    steps = simulate_flow(config)
    expected = ["ROMANTIC_HOUSE", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 组合 2 仅浪漫满屋验证通过: {' -> '.join(steps)}")


def test_free_gift_only():
    print("--- [Check 3A: 仅每日免费礼包] ---")
    steps = simulate_flow({"free_gift": True})
    expected = ["FREE_GIFT", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 每日免费礼包可独立启用并正常结束: {' -> '.join(steps)}")


def test_reindeer_fish_only():
    print("--- [Check 3B: 仅驯鹿鱼送收礼物] ---")
    steps = simulate_flow({"reindeer_fish": True})
    expected = ["REINDEER_FISH", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 驯鹿鱼送收礼物可独立启用并正常推进: {' -> '.join(steps)}")


def test_combination_3():
    print("--- [Check 4: 组合 3 - 仅金海豚] ---")
    config = {"golden_dolphin": True}
    steps = simulate_flow(config)
    expected = ["GOLDEN_DOLPHIN", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 组合 3 仅金海豚验证通过: {' -> '.join(steps)}")


def test_combination_4():
    print("--- [Check 5: 组合 4 - 钓鱼达人 + 浪漫满屋] ---")
    config = {"fishing": True, "romantic_house": True}
    steps = simulate_flow(config)
    expected = ["FISHING", "ROMANTIC_HOUSE", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 组合 4 组合跳跃验证通过: {' -> '.join(steps)}")


def test_combination_5_empty():
    print("--- [Check 6: 组合 5 - 未勾选任何任务] ---")
    config = {}
    steps = simulate_flow(config)
    expected = ["ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 组合 5 空勾选安全跳过验证通过: {' -> '.join(steps)}")


def test_combination_band_fish_only():
    print("--- [Check 7: 组合 6 - 仅乐队鱼 (Pass 1 -> Pass 2)] ---")
    config = {"band_fish": True}
    steps = simulate_flow(config)
    expected = ["BAND_FISH_PASS1", "BAND_FISH_PASS2", "ALL_DONE"]
    assert steps == expected, f"Visited steps mismatch: {steps} vs {expected}"
    print(f"[PASS] 组合 6 仅乐队鱼两阶段验证通过: {' -> '.join(steps)}")


def test_node_override_mode():
    print("--- [Check 8: UI Pipeline Override 节点模式读取] ---")
    mock_pipeline = {
        "DailyRoutineEnableFreeGift": {"enabled": True},
        "DailyRoutineEnableReindeerFish": {"enabled": True},
        "DailyRoutineEnableBandFish": {"enabled": False},
        "DailyRoutineEnableGoldenDolphin": {"enabled": True},
        "DailyRoutineEnableFishing": {"enabled": False},
        "DailyRoutineEnableRomanticHouse": {"enabled": True},
    }
    init_action = InitDailyRoutineAction()
    ctx = MockContext(mock_pipeline)
    arg = MockArg("null")
    init_action.run(ctx, arg)

    assert daily_routine_state["step"] == "FREE_GIFT"
    assert daily_routine_state["queue"] == ["REINDEER_FISH", "GOLDEN_DOLPHIN", "ROMANTIC_HOUSE"]

    advance_daily_routine_step("FreeGift", "DONE")
    assert daily_routine_state["step"] == "REINDEER_FISH"

    advance_daily_routine_step("ReindeerFish", "DONE")
    assert daily_routine_state["step"] == "GOLDEN_DOLPHIN"

    advance_daily_routine_step("GoldenDolphin", "DONE")
    assert daily_routine_state["step"] == "ROMANTIC_HOUSE"

    advance_daily_routine_step("RomanticHouse", "DONE")
    assert daily_routine_state["step"] == "ALL_DONE"

    DailyRoutineFinishAction().run(ctx, arg)
    assert daily_routine_state["active"] is False
    print("[PASS] UI Pipeline Override 模式下节点状态解析与流转验证通过!")


def test_standalone_non_active():
    print("--- [Check 9: 独立运行兼容性 (Non-Active)] ---")
    daily_routine_state["active"] = False
    daily_routine_state["step"] = "INIT"

    rh_exit = RomanticHouseExitToTankAction()
    ctx = MockContext()
    arg = MockArg("null")
    res = rh_exit.run(ctx, arg)
    assert res is True
    assert daily_routine_state["active"] is False
    assert daily_routine_state["step"] == "INIT"

    advance_daily_routine_step("BandFish", "DONE")
    assert daily_routine_state["step"] == "INIT"
    print("[PASS] 独立执行保护验证通过，未激活日常收尾时各子任务互不干扰!")


def test_band_fish_after_exit_modes():
    print("--- [Check 10: 乐队鱼退出后的运行模式分流] ---")
    ctx = MockContext()
    arg = MockArg("null")
    daily_reco = CheckBandFishDailyRoutineReco()
    pending_reco = CheckBandFishStandalonePendingReco()
    done_reco = CheckBandFishStandaloneDoneReco()

    daily_routine_state["active"] = True
    from agent.runtime_state import band_fish_state
    band_fish_state["status"] = "PENDING"
    band_fish_state["performance_finished"] = False
    assert daily_reco.analyze(ctx, arg) is not None
    assert pending_reco.analyze(ctx, arg) is None
    assert done_reco.analyze(ctx, arg) is None

    daily_routine_state["active"] = False
    assert daily_reco.analyze(ctx, arg) is None
    assert pending_reco.analyze(ctx, arg) is not None
    assert done_reco.analyze(ctx, arg) is None

    band_fish_state["status"] = "DONE"
    band_fish_state["performance_finished"] = True
    assert pending_reco.analyze(ctx, arg) is None
    assert done_reco.analyze(ctx, arg) is not None
    print("[PASS] 独立待接受会重进，独立完成会正常结束，日常模式会回调度器")


def main():
    print("=" * 70)
    print("  MaaHappyFish 日常收尾 Phase 2 调度器测试套件")
    print("=" * 70)
    test_pipeline_topology()
    test_combination_1()
    test_combination_2()
    test_free_gift_only()
    test_reindeer_fish_only()
    test_combination_3()
    test_combination_4()
    test_combination_5_empty()
    test_combination_band_fish_only()
    test_node_override_mode()
    test_standalone_non_active()
    test_band_fish_after_exit_modes()
    print("=" * 70)
    print("  [PASS] 调度器全部 12 项测试用例 100% 验证通过!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
