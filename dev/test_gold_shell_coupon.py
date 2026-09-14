#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金贝壳券 (GoldShellCouponTask) 离线安全与状态机单测套件
覆盖用户指定的全部 7 个核心测试场景:
Case 1: 分类页不能误判成金贝壳主页 (分类页特征命中时 CheckGoldShellPageReco 必须返回 None)
Case 2: 金贝壳主页专属门禁 (非分类页且有返回按钮时 CheckGoldShellPageReco 稳定命中)
Case 3: 有兑换 (点击兑换后流向 PostExchangeRouter，按钮消失后验证通过流向返回)
Case 4: 点击兑换未生效 (按钮依然存在且无弹窗，流向 GoldShellCouponExchangeVerifyFailed 熔断)
Case 5: 无兑换 (主页门禁成立但未识别到兑换，流向 NoExchange 正常返回)
Case 6: DoneAction 重复执行幂等保护 (连续调用多次，DailyRoutine 队列仅推进一次)
Case 7: Standalone 独立运行安全 (active=False 时多次执行 DoneAction 不污染队列)
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional, NamedTuple

# 仅添加项目根目录至 sys.path，保证统一使用 agent.* 模块命名空间
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.runtime_state import daily_routine_state
from agent.my_action import GoldShellCouponDoneAction, advance_daily_routine_step
from agent.my_reco import (
    CheckGoldShellPageReco,
    CheckExchangeDisappearedReco,
    CheckDailyRoutineActiveReco,
)


class MockRecoResult:
    def __init__(self, hit: bool = True, box=(0, 0, 100, 100)):
        self.hit = hit
        self.box = box


class MockContext:
    def __init__(self, hit_nodes=None):
        self.hit_nodes = hit_nodes or {}

    def run_recognition(self, node_name: str, image=None):
        if node_name in self.hit_nodes:
            val = self.hit_nodes[node_name]
            if isinstance(val, bool):
                return MockRecoResult(hit=val)
            elif isinstance(val, tuple) or isinstance(val, list):
                return MockRecoResult(hit=True, box=val)
            elif val is None:
                return MockRecoResult(hit=False)
            return val
        return MockRecoResult(hit=False)


class MockArg:
    def __init__(self, param="{}"):
        self.custom_action_param = param if isinstance(param, str) else json.dumps(param)
        self.custom_recognition_param = self.custom_action_param
        self.image = None


def load_pipeline():
    p_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "resource", "pipeline", "features", "gold_shell_coupon.json"
    )
    with open(p_path, "r", encoding="utf-8") as f:
        return json.load(f)


GLOBAL_POPUP_HANDLERS = {
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
}


def business_next(node):
    return [n for n in node.get("next", []) if n not in GLOBAL_POPUP_HANDLERS]


def test_case_1_category_page_never_misjudged():
    """Case 1: 分类页不能误判成金贝壳主页"""
    print("\n--- [Test Case 1: 分类页不能误判成金贝壳主页] ---")
    reco = CheckGoldShellPageReco()

    # 场景 1A: 贝壳分类页小章鱼命中 (无论返回按钮是否存在，必须返回 None)
    ctx_octopus = MockContext({
        "GoldShellCouponVerifyCategoryPage": MockRecoResult(hit=True, box=(498, 80, 280, 191)),
        "GoldShellCouponReturnButtonCheck": MockRecoResult(hit=True, box=(0, 0, 250, 150)),
    })
    res_1a = reco.analyze(ctx_octopus, MockArg())
    assert res_1a is None, "Case 1A 失败: 分类页小章鱼存在时，不得误判为金贝壳主页"

    # 场景 1B: 分类页进入按钮命中 (小章鱼漏检但进入按钮在，必须返回 None)
    ctx_enter = MockContext({
        "GoldShellCouponVerifyCategoryPage": MockRecoResult(hit=False),
        "GoldShellCouponEnterGold": MockRecoResult(hit=True, box=(904, 579, 108, 40)),
        "GoldShellCouponReturnButtonCheck": MockRecoResult(hit=True, box=(0, 0, 250, 150)),
    })
    res_1b = reco.analyze(ctx_enter, MockArg())
    assert res_1b is None, "Case 1B 失败: 分类页进入按钮存在时，不得误判为金贝壳主页"

    # 场景 1C: 主鱼缸主界面特征命中 (必须返回 None)
    ctx_tank = MockContext({
        "GoldShellCouponVerifyTankInternal": MockRecoResult(hit=True, box=(0, 200, 150, 400)),
        "GoldShellCouponReturnButtonCheck": MockRecoResult(hit=True, box=(0, 0, 250, 150)),
    })
    res_1c = reco.analyze(ctx_tank, MockArg())
    assert res_1c is None, "Case 1C 失败: 主鱼缸特征存在时，不得误判为金贝壳主页"

    print("  >>> PASS: Case 1 验证通过 (分类页小章鱼/进入按钮/主鱼缸特征绝不误判成金贝壳主页)")


def test_case_2_gold_page_exclusive_gatekeeper():
    """Case 2: 金贝壳主页专属门禁稳定命中"""
    print("\n--- [Test Case 2: 金贝壳主页专属门禁] ---")
    reco = CheckGoldShellPageReco()

    # 场景 2: 真实金贝壳页: 分类页特征与主鱼缸特征均不存在，返回按钮存在
    ctx_gold = MockContext({
        "GoldShellCouponVerifyCategoryPage": MockRecoResult(hit=False),
        "GoldShellCouponEnterGold": MockRecoResult(hit=False),
        "GoldShellCouponVerifyTankInternal": MockRecoResult(hit=False),
        "GoldShellCouponReturnButtonCheck": MockRecoResult(hit=True, box=(0, 0, 189, 146)),
    })
    res_2 = reco.analyze(ctx_gold, MockArg())
    assert res_2 is not None, "Case 2 失败: 真实金贝壳页必须稳定命中门禁"
    assert res_2 == (0, 0, 189, 146), f"Case 2 失败: 命中区域不匹配 -> {res_2}"

    print("  >>> PASS: Case 2 验证通过 (真实金贝壳页稳定命中专属门禁)")


def test_case_3_exchange_success_verification():
    """Case 3: 有兑换 -> 点击兑换 -> PostExchange 验证 -> 验证成功后才能返回"""
    print("\n--- [Test Case 3: 有兑换成功验证流转] ---")
    pdata = load_pipeline()

    # 1. 验证 Pipeline 节点拓扑
    node_check = pdata["GoldShellCouponCheckExchange"]
    assert business_next(node_check) == ["GoldShellCouponPostExchangeRouter"], "点击兑换后必须流向 PostExchangeRouter"
    
    post_router = pdata["GoldShellCouponPostExchangeRouter"]
    assert business_next(post_router) == [
        "GoldShellCouponRewardPopup",
        "GoldShellCouponExchangeDisappeared",
        "GoldShellCouponExchangeVerifyFailed",
    ], "PostExchangeRouter 必须包含弹窗判定、按钮消失判定与失败兜底"

    # 2. 方案 A: 兑换按钮消失识别器验证
    reco_disappear = CheckExchangeDisappearedReco()
    ctx_disappeared = MockContext({
        "GoldShellCouponCheckExchange": MockRecoResult(hit=False),  # 兑换按钮未检出，说明已消失
    })
    hit_disappear = reco_disappear.analyze(ctx_disappeared, MockArg())
    assert hit_disappear is not None, "Case 3 失败: 按钮消失时 CheckExchangeDisappearedReco 必须命中"

    # 3. 验证消失后流向返回分类页节点
    node_disappeared = pdata["GoldShellCouponExchangeDisappeared"]
    assert business_next(node_disappeared) == ["GoldShellCouponReturnCategory"], "按钮消失验证通过后必须流向返回分类页"

    # 4. 方案 B: 结算弹窗关闭后流向返回分类页
    node_popup = pdata["GoldShellCouponRewardPopup"]
    assert business_next(node_popup) == ["GoldShellCouponReturnCategory"], "结算弹窗处理后必须流向返回分类页"

    print("  >>> PASS: Case 3 验证通过 (点击兑换经过 PostExchangeRouter，按钮消失/弹窗确认后流向返回)")


def test_case_4_exchange_unresponsive_verify_failed():
    """Case 4: 点击兑换未生效 (兑换按钮依然存在且无弹窗) -> 必须进入失败熔断"""
    print("\n--- [Test Case 4: 点击兑换未生效防假完成熔断] ---")
    pdata = load_pipeline()

    # 1. 模拟兑换按钮依然存在: CheckExchangeDisappearedReco 必须返回 None
    reco_disappear = CheckExchangeDisappearedReco()
    ctx_still_there = MockContext({
        "GoldShellCouponCheckExchange": MockRecoResult(hit=True, box=(1136, 41, 91, 35)),
    })
    res_still_there = reco_disappear.analyze(ctx_still_there, MockArg())
    assert res_still_there is None, "Case 4 失败: 兑换按钮仍在时 CheckExchangeDisappearedReco 不得命中"

    # 2. 验证 PostExchangeRouter 下一顺位命中 GoldShellCouponExchangeVerifyFailed
    post_router = pdata["GoldShellCouponPostExchangeRouter"]
    candidates = business_next(post_router)
    assert candidates[-1] == "GoldShellCouponExchangeVerifyFailed", "PostExchangeRouter 兜底必须是 ExchangeVerifyFailed"

    node_failed = pdata["GoldShellCouponExchangeVerifyFailed"]
    assert node_failed.get("action") == "StopTask", "Case 4 失败: ExchangeVerifyFailed 必须为 StopTask 熔断动作"
    assert "next" not in node_failed, "Case 4 失败: ExchangeVerifyFailed 绝不能有 next 节点，杜绝流向返回或 DONE"

    print("  >>> PASS: Case 4 验证通过 (点击兑换未生效时严禁假完成，安全跌入 StopTask 熔断)")


def test_case_5_no_exchange_flow():
    """Case 5: 无兑换 (主页门禁成立但多次未识别到兑换) -> NoExchange -> 正常返回"""
    print("\n--- [Test Case 5: 无兑换正常返回分支] ---")
    pdata = load_pipeline()

    # 1. 检查 CheckExchange 未命中后进入重试
    check_node = pdata["GoldShellCouponCheckExchange"]
    assert "GoldShellCouponExchangeRetry" in check_node.get("on_error", []), "CheckExchange 失败必须进入重试"

    # 2. 检查重试未命中后进入 NoExchange
    retry_node = pdata["GoldShellCouponExchangeRetry"]
    assert "GoldShellCouponNoExchange" in retry_node.get("on_error", []), "ExchangeRetry 失败必须进入 NoExchange"

    # 3. 检查 NoExchange 流向两级返回
    no_ex_node = pdata["GoldShellCouponNoExchange"]
    assert business_next(no_ex_node) == ["GoldShellCouponReturnCategory"], "NoExchange 必须正常流向返回分类页"

    # 4. 验证两级返回流水线完整性
    ret_cat = pdata["GoldShellCouponReturnCategory"]
    assert business_next(ret_cat) == ["GoldShellCouponVerifyCategoryAfterReturn"]
    ver_cat = pdata["GoldShellCouponVerifyCategoryAfterReturn"]
    assert business_next(ver_cat) == ["GoldShellCouponReturnTank"]
    ret_tank = pdata["GoldShellCouponReturnTank"]
    assert business_next(ret_tank) == ["GoldShellCouponVerifyTank"]

    print("  >>> PASS: Case 5 验证通过 (无兑换分支经由 NoExchange 正常执行两级返回)")


def test_case_6_done_action_idempotency():
    """Case 6: DoneAction 连续调用至少两次，DailyRoutine 队列仅推进一次"""
    print("\n--- [Test Case 6: DoneAction 幂等性与重复执行保护] ---")
    action = GoldShellCouponDoneAction()
    ctx = MockContext()
    arg = MockArg()

    # 初始状态设置: 日常收尾激活，当前步为 GOLD_SHELL_COUPON
    daily_routine_state["active"] = True
    daily_routine_state["step"] = "GOLD_SHELL_COUPON"
    daily_routine_state["queue"] = ["GOLDEN_DOLPHIN", "FISHING"]
    daily_routine_state["tasks"]["GoldShellCoupon"]["status"] = "IDLE"

    # 第一次调用: 正常推进
    res1 = action.run(ctx, arg)
    assert res1 is True
    assert daily_routine_state["tasks"]["GoldShellCoupon"]["status"] == "DONE"
    assert daily_routine_state["step"] == "GOLDEN_DOLPHIN", f"步进错误: {daily_routine_state['step']}"
    assert daily_routine_state["queue"] == ["FISHING"], f"队列错误: {daily_routine_state['queue']}"

    # 第二次调用 (模拟断点重试/重复触发): 幂等保护生效，不推进队列
    res2 = action.run(ctx, arg)
    assert res2 is True
    assert daily_routine_state["tasks"]["GoldShellCoupon"]["status"] == "DONE"
    assert daily_routine_state["step"] == "GOLDEN_DOLPHIN", f"重复调用导致 step 异常推进: {daily_routine_state['step']}"
    assert daily_routine_state["queue"] == ["FISHING"], f"重复调用导致 queue 异常弹出: {daily_routine_state['queue']}"

    # 第三次调用: 再次验证稳定性
    res3 = action.run(ctx, arg)
    assert res3 is True
    assert daily_routine_state["step"] == "GOLDEN_DOLPHIN"
    assert daily_routine_state["queue"] == ["FISHING"]

    print("  >>> PASS: Case 6 验证通过 (DoneAction 连续调用 3 次，队列仅推进 1 次，幂等守卫 100% 生效)")


def test_case_7_standalone_safety():
    """Case 7: Standalone 独立运行安全 (active=False 时多次调用 DoneAction 不污染队列)"""
    print("\n--- [Test Case 7: Standalone 独立运行安全] ---")
    action = GoldShellCouponDoneAction()
    ctx = MockContext()
    arg = MockArg()

    # 独立运行模式: active=False
    daily_routine_state["active"] = False
    daily_routine_state["step"] = "INIT"
    daily_routine_state["queue"] = ["REMAINING_TASK_DO_NOT_TOUCH"]

    # 连续调用两次
    assert action.run(ctx, arg) is True
    assert action.run(ctx, arg) is True

    # 验证日常收尾状态未被修改
    assert daily_routine_state["active"] is False
    assert daily_routine_state["step"] == "INIT", "独立运行不得修改 daily_routine_state['step']"
    assert daily_routine_state["queue"] == ["REMAINING_TASK_DO_NOT_TOUCH"], "独立运行不得修改 daily_routine_state['queue']"

    # 验证 CheckDailyRoutineActiveReco 在独立模式下返回 None
    active_reco = CheckDailyRoutineActiveReco()
    assert active_reco.analyze(ctx, arg) is None, "独立模式下 CheckDailyRoutineActiveReco 必须返回 None"

    print("  >>> PASS: Case 7 验证通过 (active=False 独立运行下多次执行 DoneAction 绝不污染日常收尾队列)")


def run_all():
    print("=" * 70)
    print("=== [GoldShellCouponTask] 离线安全性全量测试套件开始 ===")
    print("=" * 70)

    test_case_1_category_page_never_misjudged()
    test_case_2_gold_page_exclusive_gatekeeper()
    test_case_3_exchange_success_verification()
    test_case_4_exchange_unresponsive_verify_failed()
    test_case_5_no_exchange_flow()
    test_case_6_done_action_idempotency()
    test_case_7_standalone_safety()

    print("\n" + "=" * 70)
    print("=== [ALL 7 CASES PASSED 100%] 金贝壳券代码安全性加固验证全部通过！ ===")
    print("=" * 70)


if __name__ == "__main__":
    run_all()
