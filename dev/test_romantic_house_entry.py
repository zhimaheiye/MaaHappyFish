# -*- coding: utf-8 -*-
"""浪漫满屋入口可靠性语义回归测试（2026-09-18 入口改造）。

背景：主鱼缸里的鱼会游动，遮挡海藻/珊瑚与气泡；Click Action.Succeeded 只代表
点击发出，不代表真的进入浪漫满屋主页。入口策略改为：

    确认主鱼缸（主界面特征.png 门禁）
    → 固定位置点击海藻 [842,554,126,56]
    → 固定位置点击气泡 [878,391,71,57]
    → RomanticHouseInHomePage（浪漫满屋_热恋时刻.png）验证真正进入
        命中       → 继续业务
        仍在主鱼缸 → 重新走整套入口（不限小重试上限，Stop 正常停止）
        未知页面   → 短暂等待重走 Router；仍未知则安全失败，绝不盲点固定坐标

本测试用页面级识别语义驱动真实 Pipeline 图（assets/resource/pipeline/features/romantic_house.json），
模拟 MaaFramework next 列表语义（候选按序、首个命中生效、全部未命中走 on_error）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
ROMANTIC_HOUSE_PATH = ROOT / "assets/resource/pipeline/features/romantic_house.json"

GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]

MAIN_TANK = "main"
HOME_PAGE = "home"          # 浪漫满屋活动主页
STAGE_PAGE = "stage"        # 热恋时刻舞台
UNKNOWN_PAGE = "unknown"    # 动画/弹窗等未知状态

SEAWEED_TARGET = [842, 554, 126, 56]
BUBBLE_TARGET = [878, 391, 71, 57]
OLD_BUBBLE_TARGET = [874, 387, 71, 65]

# 各节点识别语义：其 recognition 在哪些页面能命中。
# - RomanticHouseInFishTank / RomanticHouseDone：主界面特征.png，只命中主鱼缸；
# - RomanticHouseInHomePage / RomanticHouseCheckInHome：热恋时刻模板，只命中活动主页；
# - CheckDone（OCR 10/10）/ TryBless / NextCouple：只在舞台命中；
# - DirectHit 节点恒命中。
ALWAYS_HIT = {
    "RomanticHouseWaitBubble",
    "RomanticHouseTransientWait",
    "RomanticHouseAbort",
    "RomanticHouseStartRouter",  # DoNothing 状态路由器，识别恒命中，由候选列表决定走向
}
RECO_PAGES = {
    "RomanticHouseInFishTank": {MAIN_TANK},
    "RomanticHouseDone": {MAIN_TANK},
    "RomanticHouseInHomePage": {HOME_PAGE},
    "RomanticHouseCheckInHome": {HOME_PAGE},
    "RomanticHouseCheckDone": {STAGE_PAGE},
    "RomanticHouseTryBless": {STAGE_PAGE},
    "RomanticHouseNextCouple": {STAGE_PAGE},
}
# 入口状态机的终点（舞台内部祝福业务不属于入口链）。
TERMINAL_OUTCOMES = {
    "RomanticHouseInHomePage": "in_home_page",
    "RomanticHouseAbort": "abort_stop_task",
    # Done 的双出口定义在 daily_routine.json（Custom reco 分流），到达即视为出口终点
    "DailyRoutineReturnIfActive": "daily_routine_exit",
    "DailyRoutineStandaloneDone": "daily_routine_exit",
}


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


class RomanticHouseEntrySimulator:
    """按 Maa next 列表语义驱动真实 romantic_house.json 入口链。"""

    def __init__(self, pipeline, after_bubble_click):
        # after_bubble_click(click_round) -> 本轮气泡点击后的真实页面
        self.pipeline = pipeline
        self.after_bubble_click = after_bubble_click
        self.visited = []
        self.clicks = []          # (节点名, 固定 target)——固定坐标点击记录
        self.rounds = 0           # 完整入口轮次（每轮 = 海藻 + 气泡）
        self.page = None
        self.outcome = None

    def reco_hit(self, name):
        if name in ALWAYS_HIT:
            return True
        if name in RECO_PAGES:
            return self.page in RECO_PAGES[name]
        if name in TERMINAL_OUTCOMES:
            return True  # 双出口等 DirectHit 型终点恒命中
        raise AssertionError(f"入口链意外到达节点: {name}")

    def _follow(self, name):
        self.visited.append(name)
        if name in TERMINAL_OUTCOMES:
            self.outcome = TERMINAL_OUTCOMES[name]
            return
        node = self.pipeline[name]
        if node.get("action") == "StopTask":
            self.outcome = TERMINAL_OUTCOMES[name]
            return
        if node.get("action") == "Click":
            self.clicks.append((name, list(node["target"])))
            if name == "RomanticHouseInFishTank":
                self.page = MAIN_TANK  # 海藻点击发生在主鱼缸内
            elif name == "RomanticHouseWaitBubble":
                self.rounds += 1
                self.page = self.after_bubble_click(self.rounds)
        for cand in business_next(node):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        for cand in node.get("on_error", []):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        # StartRouter 等节点候选全败且无 on_error：任务安全失败（Maa 原生行为）
        self.outcome = "safe_fail"

    def run_from_main_tank(self):
        self.page = MAIN_TANK
        assert self.reco_hit("RomanticHouseInFishTank"), "主鱼缸上门禁必须可识别"
        self._follow("RomanticHouseInFishTank")
        return self


def run_tests():
    pipeline = json.loads(ROMANTIC_HOUSE_PATH.read_text(encoding="utf-8"))

    # ---- 静态契约：入口 target 锁定，旧坐标与珊瑚/气泡模板退出生产入口 ----
    in_tank = pipeline["RomanticHouseInFishTank"]
    assert in_tank["recognition"] == "TemplateMatch"
    assert in_tank["template"] == "主界面特征.png"
    assert in_tank["roi"] == [0, 200, 150, 400]
    assert in_tank["threshold"] == 0.7
    assert in_tank["action"] == "Click"
    assert in_tank["target"] == SEAWEED_TARGET
    assert "max_hit" not in in_tank, "入口重试不得设置很小上限"
    assert in_tank.get("on_error") == ["RomanticHouseAbort"]

    wait_bubble = pipeline["RomanticHouseWaitBubble"]
    assert wait_bubble["recognition"] == "DirectHit"
    assert wait_bubble["action"] == "Click"
    assert wait_bubble["target"] == BUBBLE_TARGET
    assert business_next(wait_bubble) == ["RomanticHouseInHomePage", "RomanticHouseInFishTank"]

    transient = pipeline["RomanticHouseTransientWait"]
    assert transient["recognition"] == "DirectHit"
    assert transient["action"] == "DoNothing", "未知页面等待节点绝不下发点击"
    assert business_next(transient) == ["RomanticHouseStartRouter"]

    done = pipeline["RomanticHouseDone"]
    assert done["template"] == "主界面特征.png", "退出确认不得再依赖珊瑚模板"
    assert done["roi"] == [0, 200, 150, 400]
    assert done["custom_action"] == "RomanticHouseExitToTankAction"

    assert "RomanticHouseClickBubbleFallback" not in pipeline, "旧盲点兜底节点必须移除"
    dumped = json.dumps(pipeline, ensure_ascii=False)
    assert str(OLD_BUBBLE_TARGET) not in dumped, "旧气泡坐标不得残留"
    assert "浪漫满屋_珊瑚.png" not in dumped, "珊瑚模板不得再作为生产门禁"
    assert "浪漫满屋_气泡.png" not in dumped, "气泡模板不得再作为生产门禁"
    assert "RomanticHouseInHomePage" in business_next(pipeline["RomanticHouseStartRouter"])
    assert "RomanticHouseInFishTank" in business_next(pipeline["RomanticHouseStartRouter"])
    # 模板文件本身保留（历史兼容/调试）
    assert (ROOT / "assets/resource/image/浪漫满屋_珊瑚.png").is_file()
    assert (ROOT / "assets/resource/image/浪漫满屋_气泡.png").is_file()

    def fixed_targets(sim):
        return [tuple(t) for _, t in sim.clicks]

    # ---- Case 1：第一次直接成功 ----
    sim = RomanticHouseEntrySimulator(pipeline, lambda n: HOME_PAGE).run_from_main_tank()
    assert sim.outcome == "in_home_page", sim.visited
    seaweed = [c for c in sim.clicks if c[0] == "RomanticHouseInFishTank"]
    bubble = [c for c in sim.clicks if c[0] == "RomanticHouseWaitBubble"]
    assert len(seaweed) == 1 and len(bubble) == 1
    assert "RomanticHouseTransientWait" not in sim.visited
    assert "RomanticHouseAbort" not in sim.visited
    assert fixed_targets(sim) == [tuple(SEAWEED_TARGET), tuple(BUBBLE_TARGET)]
    print("[PASS] Case 1 第一次直接成功：海藻/气泡各点击 1 次，无重试，进入主页业务")

    # ---- Case 2：第一次被鱼挡住，第二轮成功 ----
    sim = RomanticHouseEntrySimulator(
        pipeline, lambda n: HOME_PAGE if n >= 2 else MAIN_TANK
    ).run_from_main_tank()
    assert sim.outcome == "in_home_page", sim.visited
    assert len(sim.clicks) == 4, sim.clicks  # 2 轮 x (海藻+气泡)
    assert sim.rounds == 2
    assert sim.visited.count("RomanticHouseInFishTank") == 2
    assert "RomanticHouseAbort" not in sim.visited
    assert set(fixed_targets(sim)) == {tuple(SEAWEED_TARGET), tuple(BUBBLE_TARGET)}
    print("[PASS] Case 2 被挡一次后重试成功：整套入口自动重试，未 Abort")

    # ---- Case 3：连续多轮失败后成功 ----
    sim = RomanticHouseEntrySimulator(
        pipeline, lambda n: HOME_PAGE if n >= 4 else MAIN_TANK
    ).run_from_main_tank()
    assert sim.outcome == "in_home_page", sim.visited
    assert sim.rounds == 4
    assert len(sim.clicks) == 8
    assert "RomanticHouseAbort" not in sim.visited
    print("[PASS] Case 3 连续 3 轮被挡后成功：持续重试不提前结束")

    # ---- Case 4：未知页面 ----
    sim = RomanticHouseEntrySimulator(pipeline, lambda n: UNKNOWN_PAGE).run_from_main_tank()
    assert sim.outcome == "safe_fail", sim.visited
    assert len(sim.clicks) == 2, "未知页面上不得继续固定坐标点击"
    assert sim.rounds == 1
    assert "RomanticHouseTransientWait" in sim.visited, "未知名页面应短暂等待重走 Router"
    assert "RomanticHouseAbort" not in sim.visited, "等待后由 Router 全败安全失败，无需 StopTask"
    print("[PASS] Case 4 未知页面：短暂等待重走 Router，Router 全败安全失败，绝不盲点")

    # ---- Case 5：退出后主鱼缸确认（珊瑚不可见也必须完成） ----
    sim = RomanticHouseEntrySimulator(pipeline, lambda n: HOME_PAGE)  # 复用评估器结构
    sim.page = MAIN_TANK
    # 模拟 ExitHome 点击后回到主鱼缸：评估 ExitHome.next 候选
    exit_home_next = business_next(pipeline["RomanticHouseExitHome"])
    hit = next(name for name in exit_home_next if sim.reco_hit(name))
    assert hit == "RomanticHouseDone", exit_home_next
    sim._follow(hit)
    assert sim.outcome == "daily_routine_exit"  # Done 确认主鱼缸后进入双出口
    assert sim.clicks == [], "Done 只确认主鱼缸并执行 Action，不得再点击入口"
    # 双出口候选仍在（推进 DailyRoutine / 独立完成）
    assert business_next(pipeline["RomanticHouseDone"]) == [
        "DailyRoutineReturnIfActive",
        "DailyRoutineStandaloneDone",
    ]
    print("[PASS] Case 5 退出确认：主界面特征命中即执行 ExitToTankAction，不再要求珊瑚可见")

    print("[PASS] 浪漫满屋入口重试状态机 5 项语义场景全部通过")


if __name__ == "__main__":
    run_tests()
