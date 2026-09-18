# -*- coding: utf-8 -*-
"""好友摸宝"快捷摸宝"分支语义回归测试（2026-09-18）。

业务契约：
- 快捷摸宝可用 → 点击一次 → 无论当前好友体力是否耗尽，本好友处理结束 → 下一位；
- 快捷收取后"仍有剩余体力"是正常业务状态，不是 error，不得回退气泡模式；
- 快捷键一开始不可用 → 保持原金币气泡图像模式（12 次无气泡切下一位）；
- 切好友后 attempts / bubble_miss_count 重置、好友序号 +1（复用现有链）。

页面识别语义（真实 friend_gem.json 图驱动）：
- OCR "刷新体力"（Exhausted/QuickCollectExhausted/StartInFriendTank）只命中体力耗尽页；
- 快捷键可用/不可用模板只在好友鱼缸页命中（耗尽页由 Exhausted 候选优先接管）；
- 金币气泡只在好友鱼缸页且可见时命中；
- NextFriend（好友_下一位按钮）在好友鱼缸页恒可识别。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
FRIEND_GEM_PATH = ROOT / "assets/resource/pipeline/features/friend_gem.json"

GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


from agent.my_action import (
    StepFriendGemIndexAction,
    ResetFriendGemAttemptsAction,
    RecordFriendGemBubbleMissAction,
    InitFriendGemStateAction,
)
from agent.my_reco import CheckFriendGemBubbleMissLimitReco, CheckFriendGemLimitReco


class MockArg:
    def __init__(self, param=None):
        self.custom_action_param = json.dumps(param or {})
        self.custom_recognition_param = self.custom_action_param


class MockContext:
    def override_pipeline(self, data):
        self.override = data


class FriendGemSimulator:
    """按 Maa next 列表语义驱动真实 friend_gem.json。

    page 字典字段：
      kind: "tank"（有体力）| "exhausted"（体力耗尽）
      quick_available: 快捷摸宝按钮可用性
      bubble_visible: 金币气泡是否可见
    """

    def __init__(self, pipeline, page, bubble_reco, limit_reco, after_quick_click=None):
        self.pipeline = pipeline
        self.page = page
        self.bubble_reco = bubble_reco
        self.limit_reco = limit_reco
        self.after_quick_click = after_quick_click
        self.visited = []
        self.clicks = []
        self.outcome = None

    def reco_hit(self, name):
        if name in ("FriendGemFriendRouter", "FriendGemImageFallbackRouter",
                    "FriendGemWaitForBubble", "FriendGemStepIndex", "FriendGemResetAttempts",
                    "FriendGemRecordAttempt", "FriendGemQuickCollectPostRouter",
                    "FriendGemQuickCollectPartialDone"):
            return True  # DirectHit 型节点
        if name in ("FriendGemExhausted", "FriendGemQuickCollectExhausted"):
            return self.page["kind"] == "exhausted"  # OCR "刷新体力"
        if name == "FriendGemQuickCollectAvailable":
            return self.page["kind"] == "tank" and self.page["quick_available"]
        if name == "FriendGemQuickCollectUnavailable":
            return self.page["kind"] == "tank" and not self.page["quick_available"]
        if name == "FriendGemCollectBubble":
            return self.page["kind"] == "tank" and self.page["bubble_visible"]
        if name == "FriendGemBubbleMissLimitReached":
            return self.bubble_reco.analyze(MockContext(), MockArg()) is not None
        if name == "FriendGemAttemptLimitReached":
            return self.limit_reco.analyze(MockContext(), MockArg()) is not None
        if name == "FriendGemNextFriend":
            return True  # 好友_下一位 按钮恒可见
        if name in ("FriendGemAddFriendPage", "FriendGemWelcomePopup", "FriendGemSpecialPopup",
                    "FriendGemFishBabyPark", "FriendGemCheckManatee", "HangupNoonDailyFriendGem",
                    "FriendGemDone"):
            return False  # 本轮场景不涉及
        raise AssertionError(f"意外到达节点: {name}")

    def _follow(self, name):
        if name == "FriendGemFriendRouter" and "FriendGemStepIndex" in self.visited:
            # 已完成一次完整切换链（StepIndex→ResetAttempts）回到 Router：
            # 任务会继续处理下一位好友，模拟到此为止
            self.outcome = "next_friend_cycle"
            return
        self.visited.append(name)
        if name == "FriendGemDone":
            self.outcome = "done"
            return
        node = self.pipeline[name]
        if node.get("action") == "Click":
            self.clicks.append(name)
            if name == "FriendGemNextFriend":
                self.page = {"kind": "tank", "quick_available": True, "bubble_visible": False}
            elif name == "FriendGemQuickCollectAvailable" and self.after_quick_click:
                self.after_quick_click()  # 点击快捷摸宝后的真实页面变化
        if node.get("custom_action") == "StepFriendGemIndexAction":
            assert StepFriendGemIndexAction().run(MockContext(), MockArg()) is True
        if node.get("custom_action") == "ResetFriendGemAttemptsAction":
            assert ResetFriendGemAttemptsAction().run(MockContext(), MockArg()) is True
        if node.get("custom_action") == "RecordFriendGemBubbleMissAction":
            assert RecordFriendGemBubbleMissAction().run(MockContext(), MockArg()) is True
        for cand in business_next(node):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        for cand in node.get("on_error", []):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        self.outcome = "chain_exhausted"

    def run(self, start="FriendGemFriendRouter"):
        self._follow(start)
        return self


def run_tests():
    pipeline = json.loads(FRIEND_GEM_PATH.read_text(encoding="utf-8"))

    # ---- 静态契约 ----
    available = pipeline["FriendGemQuickCollectAvailable"]
    assert available["template"] == "好友摸宝快捷键_可用.png"
    assert available["threshold"] == 0.8
    assert available["roi"] == [231, 592, 123, 120], "不得修改模板/threshold/ROI"
    assert business_next(available) == ["FriendGemQuickCollectPostRouter"]

    router = pipeline["FriendGemQuickCollectPostRouter"]
    assert router["recognition"] == "DirectHit"
    assert router["action"] == "DoNothing"
    assert business_next(router) == [
        "FriendGemQuickCollectExhausted",
        "FriendGemQuickCollectPartialDone",
    ]
    exhausted = pipeline["FriendGemQuickCollectExhausted"]
    assert exhausted["recognition"] == "OCR" and exhausted["expected"] == "刷新体力"
    assert exhausted["action"] == "DoNothing"
    assert business_next(exhausted) == ["FriendGemNextFriend"]
    partial = pipeline["FriendGemQuickCollectPartialDone"]
    assert partial["recognition"] == "DirectHit"
    assert partial["action"] == "DoNothing"
    assert business_next(partial) == ["FriendGemNextFriend"]
    # 旧 error-fallback 路径彻底移除
    assert "FriendGemQuickCollectVerifyExhausted" not in pipeline
    assert "FriendGemQuickCollectVerifyFallback" not in pipeline
    # 快捷摸宝优先级保持
    router_next = business_next(pipeline["FriendGemFriendRouter"])
    assert router_next.index("FriendGemExhausted") < router_next.index("FriendGemQuickCollectAvailable")
    assert router_next.index("FriendGemQuickCollectAvailable") < router_next.index("FriendGemQuickCollectUnavailable")
    assert router_next.index("FriendGemQuickCollectUnavailable") < router_next.index("FriendGemCollectBubble")
    # 不可用仍走气泡模式；气泡 miss 上限链保持
    assert business_next(pipeline["FriendGemQuickCollectUnavailable"]) == ["FriendGemImageFallbackRouter"]
    assert pipeline["FriendGemCollectBubble"]["template"] == "金币气泡.png"
    print("[PASS] 静态契约：PostRouter 分流、旧 Fallback 删除、快捷优先级与气泡模式保持")

    from agent.runtime_state import friend_gem_state
    from agent.my_action import StepFriendGemIndexAction, ResetFriendGemAttemptsAction, RecordFriendGemBubbleMissAction, InitFriendGemStateAction
    from agent.my_reco import CheckFriendGemBubbleMissLimitReco, CheckFriendGemLimitReco

    bubble_reco = CheckFriendGemBubbleMissLimitReco()
    limit_reco = CheckFriendGemLimitReco()

    def fresh_page(quick_available=True, kind="tank", bubble_visible=False):
        return {"kind": kind, "quick_available": quick_available, "bubble_visible": bubble_visible}

    def init_state():
        friend_gem_state["attempts"] = 0
        friend_gem_state["bubble_miss_count"] = 0
        friend_gem_state["current_friend_index"] = 1

    # ---- Case 1：快捷摸宝后体力耗尽 ----
    init_state()
    sim = FriendGemSimulator(
        pipeline, fresh_page(), bubble_reco, limit_reco,
        after_quick_click=lambda: setattr(sim, "page", {"kind": "exhausted", "quick_available": False, "bubble_visible": False}),
    )
    sim._follow("FriendGemQuickCollectAvailable")  # 快捷键识别命中并点击
    assert "FriendGemQuickCollectExhausted" in sim.visited
    assert "FriendGemNextFriend" in sim.visited
    assert "FriendGemStepIndex" in sim.visited and "FriendGemResetAttempts" in sim.visited
    assert "FriendGemImageFallbackRouter" not in sim.visited
    assert "FriendGemCollectBubble" not in sim.visited
    assert "FriendGemWaitForBubble" not in sim.visited
    assert sim.outcome == "next_friend_cycle"
    print("[PASS] Case 1 快捷摸宝后体力耗尽：正常切换下一位，不进入气泡模式")

    # ---- Case 2：快捷摸宝后仍有体力（本轮核心） ----
    init_state()
    sim = FriendGemSimulator(
        pipeline, fresh_page(), bubble_reco, limit_reco,
        after_quick_click=lambda: setattr(sim, "page", {"kind": "tank", "quick_available": False, "bubble_visible": False}),
    )
    sim._follow("FriendGemQuickCollectAvailable")
    assert "FriendGemQuickCollectPartialDone" in sim.visited
    assert "FriendGemQuickCollectExhausted" not in sim.visited
    assert "FriendGemNextFriend" in sim.visited
    assert "FriendGemImageFallbackRouter" not in sim.visited, "快捷摸宝成功后禁止回退气泡模式"
    assert "FriendGemCollectBubble" not in sim.visited
    assert "FriendGemWaitForBubble" not in sim.visited
    assert sim.outcome == "next_friend_cycle", "不得以失败/错误收尾"
    print("[PASS] Case 2 快捷摸宝后仍有体力：视为正常状态，直接切换下一位，不回退气泡模式")

    # ---- Case 3：快捷键一开始不可用 → 气泡模式保持 ----
    init_state()
    sim = FriendGemSimulator(pipeline, fresh_page(quick_available=False), bubble_reco, limit_reco)
    sim._follow("FriendGemFriendRouter")
    assert "FriendGemQuickCollectUnavailable" in sim.visited
    assert "FriendGemImageFallbackRouter" in sim.visited
    assert "FriendGemQuickCollectAvailable" not in sim.visited
    print("[PASS] Case 3 快捷键一开始不可用：保持原金币气泡图像模式")

    # ---- Case 4：气泡模式连续 12 次无气泡 → 下一位 ----
    init_state()
    sim = FriendGemSimulator(pipeline, fresh_page(quick_available=False), bubble_reco, limit_reco)
    sim._follow("FriendGemFriendRouter")
    assert sim.visited.count("FriendGemWaitForBubble") == 12, "应连续 12 次无气泡等待"
    assert "FriendGemBubbleMissLimitReached" in sim.visited
    assert "FriendGemNextFriend" in sim.visited
    print("[PASS] Case 4 气泡模式连续 12 次无气泡后由 MissLimit 切下一位（原规则未破坏）")

    # ---- Case 5：切好友状态重置链（两条路径共用） ----
    init_state()
    friend_gem_state["attempts"] = 5
    friend_gem_state["bubble_miss_count"] = 12
    sim = FriendGemSimulator(pipeline, fresh_page(), bubble_reco, limit_reco)
    sim._follow("FriendGemNextFriend")
    assert "FriendGemStepIndex" in sim.visited
    assert "FriendGemResetAttempts" in sim.visited
    assert friend_gem_state["current_friend_index"] == 2
    assert friend_gem_state["attempts"] == 0
    assert friend_gem_state["bubble_miss_count"] == 0
    # 再次切换继续 +1
    sim.page = fresh_page()
    sim.visited.clear()
    sim._follow("FriendGemNextFriend")
    assert friend_gem_state["current_friend_index"] == 3
    print("[PASS] Case 5 切好友复用 StepIndex/ResetAttempts：序号 +1、attempts 与 miss 清零")

    # ---- 静态可达性：快捷摸宝成功后的全部可达节点不含气泡模式 ----
    def reachable_within_current_friend(start):
        """当前好友处理范围内的可达节点：在 FriendGemNextFriend 截断
        （切换到下一位好友后重新走 Router，由新好友自身决定快捷/气泡，属合法业务）。"""
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur in seen or cur in GLOBAL_HANDLERS:
                continue
            seen.add(cur)
            if cur == "FriendGemNextFriend":
                continue  # 当前好友结束点
            node = pipeline.get(cur, {})
            stack.extend(business_next(node))
            stack.extend(node.get("on_error", []))
        return seen

    reach = reachable_within_current_friend("FriendGemQuickCollectAvailable")
    forbidden = {"FriendGemImageFallbackRouter", "FriendGemCollectBubble",
                 "FriendGemWaitForBubble", "FriendGemBubbleMissLimitReached",
                 "FriendGemQuickCollectVerifyFallback", "FriendGemQuickCollectVerifyExhausted"}
    assert not (reach & forbidden), f"快捷摸宝后当前好友内仍可达气泡模式: {reach & forbidden}"
    assert "FriendGemNextFriend" in reach
    print("[PASS] 静态可达性：快捷摸宝成功后当前好友内绝不进入气泡模式/旧 Fallback，统一汇入 NextFriend")

    print("[PASS] 好友摸宝快捷摸宝分支 5 项语义场景 + 静态契约全部通过")


if __name__ == "__main__":
    run_tests()
