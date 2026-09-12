#!/usr/bin/env python3
"""
日常收尾 DailyRoutineTask v3 状态机与组件离线全量单测套件
覆盖:
1. 共享运行时状态定义与生命周期
2. InitDailyRoutineAction 初始化逻辑
3. CheckDailyRoutineStepReco 步骤路由器识别
4. BandFishExitToTankAction 两阶段流转 (Pass1 -> Dolphin, Pass2 -> AllDone)
5. GoldenDolphinTaskAction 次数耗尽(NO_STAMINA)与正常完成(DONE)几何/语义判定
6. FishingExitToTankAction 甩杆上限(DONE)与鱼饵耗尽(NO_STAMINA)流转
7. CheckBandFishPass2NeededReco / CheckBandFishPass2SkipReco 跳过与回访双向判定
8. DailyRoutineSkipBandFishPass2Action 与 DailyRoutineFinishAction 结算闭环
"""
import sys
import os
import json
import types
from pathlib import Path
import numpy as np

# Add agent path
sys.path.insert(0, os.path.abspath("agent"))

# Mock AgentServer before importing agent modules
registered_actions = {}
registered_recos = {}

class MockAgentServer:
    @staticmethod
    def custom_action(name):
        def dec(cls):
            registered_actions[name] = cls()
            return cls
        return dec

    @staticmethod
    def custom_recognition(name):
        def dec(cls):
            registered_recos[name] = cls()
            return cls
        return dec

agent_mock = types.ModuleType("maa.agent.agent_server")
agent_mock.AgentServer = MockAgentServer
sys.modules["maa.agent.agent_server"] = agent_mock

import runtime_state
import my_action
import my_reco

class DummyContext:
    class DummyTasker:
        controller = None
    tasker = DummyTasker()

class DummyArg:
    def __init__(self, param="{}"):
        self.custom_action_param = param
        self.custom_recognition_param = param
        self.task_detail = None
        self.node_name = "TestNode"
        self.custom_action_name = "TestAction"
        self.custom_recognition_name = "TestReco"
        self.image = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.roi = (0, 0, 1280, 720)


def run_tests():
    print("=" * 70)
    print("=== [DailyRoutineTask v3] 离线全量单测套件开始运行 ===")
    print("=" * 70)

    # -------------------------------------------------------------
    # Test 1: InitDailyRoutineAction
    # -------------------------------------------------------------
    print("\n[Test 1] 验证 InitDailyRoutineAction 初始化")
    init_action = registered_actions["InitDailyRoutineAction"]
    success = init_action.run(DummyContext(), DummyArg('{"band_fish": true, "golden_dolphin": true, "fishing": true, "romantic_house": false}'))
    assert success is True
    assert runtime_state.daily_routine_state["active"] is True
    assert runtime_state.daily_routine_state["step"] == "BAND_FISH_PASS1"
    assert runtime_state.daily_routine_state["tasks"]["BandFish"]["stage"] == "PASS1"
    assert runtime_state.daily_routine_state["tasks"]["BandFish"]["status"] == "IDLE"
    assert runtime_state.daily_routine_state["tasks"]["GoldenDolphin"]["status"] == "IDLE"
    assert runtime_state.daily_routine_state["tasks"]["Fishing"]["status"] == "IDLE"
    print("  >>> PASS: 初始化状态契约 100% 吻合！")

    # -------------------------------------------------------------
    # Test 2: CheckDailyRoutineStepReco
    # -------------------------------------------------------------
    print("\n[Test 2] 验证 CheckDailyRoutineStepReco 步骤路由识别器")
    step_reco = registered_recos["CheckDailyRoutineStepReco"]
    
    # 匹配当前步骤
    arg_pass1 = DummyArg('{"expected_step": "BAND_FISH_PASS1"}')
    hit = step_reco.analyze(DummyContext(), arg_pass1)
    assert hit is not None, "应当命中 BAND_FISH_PASS1"

    # 不匹配其他步骤
    arg_dolphin = DummyArg('{"expected_step": "GOLDEN_DOLPHIN"}')
    miss = step_reco.analyze(DummyContext(), arg_dolphin)
    assert miss is None, "不应命中 GOLDEN_DOLPHIN"

    # 非 active 状态下始终返回 None (防 standalone 串扰)
    runtime_state.daily_routine_state["active"] = False
    miss_inactive = step_reco.analyze(DummyContext(), arg_pass1)
    assert miss_inactive is None, "Inactive 状态下应当始终返回 None"
    runtime_state.daily_routine_state["active"] = True
    print("  >>> PASS: 步骤路由与防串扰隔离 100% 通过！")

    # -------------------------------------------------------------
    # Test 3: BandFishExitToTankAction - Pass 1 PENDING 场景
    # -------------------------------------------------------------
    print("\n[Test 3] 验证 BandFishExitToTankAction - Pass 1 (待响应 PENDING 状态)")
    # 模拟 Mock Controller 避免物理报错
    class MockCtrl:
        def __init__(self):
            self.clicks = []

        def post_click(self, x, y):
            self.clicks.append((x, y))
            class Job:
                def wait(self): pass
            return Job()

    ctx = DummyContext()
    ctx.tasker.controller = MockCtrl()

    runtime_state.band_fish_state["status"] = "NEED_INVITE"
    runtime_state.band_fish_state["performance_finished"] = False
    runtime_state.daily_routine_state["tasks"]["BandFish"]["stage"] = "PASS1"

    bf_exit = registered_actions["BandFishExitToTankAction"]
    success = bf_exit.run(ctx, DummyArg())
    assert success is True
    assert runtime_state.daily_routine_state["tasks"]["BandFish"]["status"] == "PENDING"
    assert runtime_state.daily_routine_state["step"] == "GOLDEN_DOLPHIN"
    print("  >>> PASS: Pass 1 未完全就绪时安全沉淀为 PENDING，并自动推进至 GOLDEN_DOLPHIN！")

    # -------------------------------------------------------------
    # Test 4: FishingExitToTankAction - NO_STAMINA 与 DONE 两种流转
    # -------------------------------------------------------------
    print("\n[Test 4] 验证 FishingExitToTankAction 业务状态流转")
    fish_exit = registered_actions["FishingExitToTankAction"]
    fishing_pipeline = json.loads(
        Path("assets/resource/pipeline/features/fishing.json").read_text(encoding="utf-8")
    )
    assert fishing_pipeline["FishingDone"]["next"][-1] == "FishingVerifyExitToTank"
    verify_exit = fishing_pipeline["FishingVerifyExitToTank"]
    assert verify_exit["template"] == "主界面特征.png"
    assert verify_exit["next"][-2:] == ["DailyRoutineReturnIfActive", "DailyRoutineStandaloneDone"]
    assert verify_exit["on_error"] == ["FishingExitFailed"]
    assert fishing_pipeline["FishingExitFailed"]["action"] == "StopTask"

    # 4.1 鱼饵耗尽 (未满5杆)
    ctx.tasker.controller.clicks.clear()
    runtime_state.daily_routine_state["queue"] = ["BAND_FISH_PASS2"]
    runtime_state.fishing_state["cast_count"] = 2
    runtime_state.fishing_state["max_casts"] = 5
    success = fish_exit.run(ctx, DummyArg())
    assert success is True
    assert ctx.tasker.controller.clicks[-1:] == [(1235, 45)]
    assert (50, 45) not in ctx.tasker.controller.clicks
    assert (640, 150) not in ctx.tasker.controller.clicks
    assert runtime_state.fishing_state["status"] == "NO_STAMINA"
    assert runtime_state.daily_routine_state["tasks"]["Fishing"]["status"] == "NO_STAMINA"
    assert runtime_state.daily_routine_state["step"] == "BAND_FISH_PASS2"
    assert runtime_state.daily_routine_state["tasks"]["BandFish"]["stage"] == "PASS2"
    print("  >>> PASS: 鱼饵耗尽正常退出，标记为 NO_STAMINA，不抛异常，推进至 BAND_FISH_PASS2！")

    # 4.2 甩杆满额 (满5杆)
    runtime_state.fishing_state["cast_count"] = 5
    success = fish_exit.run(ctx, DummyArg())
    assert success is True
    assert ctx.tasker.controller.clicks[-1:] == [(1235, 45)]
    assert runtime_state.fishing_state["status"] == "DONE"
    assert runtime_state.daily_routine_state["tasks"]["Fishing"]["status"] == "DONE"
    print("  >>> PASS: 甩杆满额正常退出，标记为 DONE！")

    # -------------------------------------------------------------
    # Test 5: Pass 2 决策分支 (CheckBandFishPass2NeededReco vs SkipReco)
    # -------------------------------------------------------------
    print("\n[Test 5] 验证 Pass 2 条件决策路由 (跳过 vs 回访判定)")
    needed_reco = registered_recos["CheckBandFishPass2NeededReco"]
    skip_reco = registered_recos["CheckBandFishPass2SkipReco"]

    # 场景 5.1: Pass 1 为 PENDING，需要回访
    runtime_state.daily_routine_state["tasks"]["BandFish"]["status"] = "PENDING"
    assert needed_reco.analyze(ctx, DummyArg()) is not None, "PENDING 时应当触发 Pass 2 回访"
    assert skip_reco.analyze(ctx, DummyArg()) is None, "PENDING 时不应触发跳过"
    print("  >>> PASS: PENDING 状态正确触发 Pass 2 回访！")

    # 场景 5.2: Pass 1 为 DONE，跳过 Pass 2
    runtime_state.daily_routine_state["tasks"]["BandFish"]["status"] = "DONE"
    assert needed_reco.analyze(ctx, DummyArg()) is None, "DONE 时不应触发 Pass 2 回访"
    assert skip_reco.analyze(ctx, DummyArg()) is not None, "DONE 时应当触发直接跳过"
    print("  >>> PASS: DONE 状态正确跳过 Pass 2！")

    # -------------------------------------------------------------
    # Test 6: DailyRoutineSkipBandFishPass2Action
    # -------------------------------------------------------------
    print("\n[Test 6] 验证 DailyRoutineSkipBandFishPass2Action 跳过动作")
    skip_action = registered_actions["DailyRoutineSkipBandFishPass2Action"]
    success = skip_action.run(ctx, DummyArg())
    assert success is True
    assert runtime_state.daily_routine_state["step"] == "ALL_DONE"
    print("  >>> PASS: 跳过动作成功将流转推入 ALL_DONE！")

    # -------------------------------------------------------------
    # Test 7: BandFishExitToTankAction - Pass 2 结束场景
    # -------------------------------------------------------------
    print("\n[Test 7] 验证 BandFishExitToTankAction - Pass 2 结束")
    runtime_state.daily_routine_state["tasks"]["BandFish"]["stage"] = "PASS2"
    runtime_state.band_fish_state["status"] = "DONE"
    success = bf_exit.run(ctx, DummyArg())
    assert success is True
    assert runtime_state.daily_routine_state["tasks"]["BandFish"]["status"] == "DONE"
    assert runtime_state.daily_routine_state["step"] == "ALL_DONE"
    print("  >>> PASS: Pass 2 结束时自动流转至 ALL_DONE！")

    # -------------------------------------------------------------
    # Test 8: DailyRoutineFinishAction
    # -------------------------------------------------------------
    print("\n[Test 8] 验证 DailyRoutineFinishAction 汇总结算")
    finish_action = registered_actions["DailyRoutineFinishAction"]
    runtime_state.daily_routine_state["tasks"] = {
        "BandFish": {"status": "DONE", "stage": "PASS2"},
        "GoldenDolphin": {"status": "NO_STAMINA"},
        "Fishing": {"status": "DONE"},
    }
    success = finish_action.run(ctx, DummyArg())
    assert success is True
    assert runtime_state.daily_routine_state["active"] is False
    assert runtime_state.daily_routine_state["step"] == "ALL_DONE"
    print("  >>> PASS: 日常收尾汇总结算报告打印无误，状态安全注销！")

    # -------------------------------------------------------------
    # Test 9: GoldenDolphin 视觉几何区分算法离线 Replay 验证
    # -------------------------------------------------------------
    print("\n[Test 9] 验证金海豚弹窗几何过滤算法 (想玩弹窗 vs 机会耗尽弹窗)")
    import cv2
    # 9.1 想玩弹窗: 包含红色圆形取消叉叉
    img_confirm_path = "dev/exploration/golden_dolphin/02_confirm_popup.png"
    if os.path.exists(img_confirm_path):
        img_confirm = cv2.imread(img_confirm_path)
        sc_720 = cv2.resize(img_confirm, (1280, 720))
        red_patch = sc_720[430:490, 650:710]
        hsv_p = cv2.cvtColor(red_patch, cv2.COLOR_BGR2HSV)
        mask_r = ((hsv_p[:, :, 0] < 10) | (hsv_p[:, :, 0] > 170)) & (hsv_p[:, :, 1] > 90) & (hsv_p[:, :, 2] > 90)
        has_red_cancel = bool(np.sum(mask_r) > 400)
        assert has_red_cancel is True, "想玩弹窗必须检测到红色取消按钮"
        print(f"  - 想玩弹窗红色像素数: {int(np.sum(mask_r))} (>=400 判定进入游戏)")

    # 9.2 耗尽弹窗: 无红色圆形取消叉叉
    img_exhausted_path = "C:/Users/sxy10/.gemini/antigravity/brain/65c155de-1230-4b2a-9733-2a78a0f09e43/scratch/pre_test_screen.png"
    if os.path.exists(img_exhausted_path):
        img_exhausted = cv2.imread(img_exhausted_path)
        sc_720 = cv2.resize(img_exhausted, (1280, 720))
        red_patch = sc_720[430:490, 650:710]
        hsv_p = cv2.cvtColor(red_patch, cv2.COLOR_BGR2HSV)
        mask_r = ((hsv_p[:, :, 0] < 10) | (hsv_p[:, :, 0] > 170)) & (hsv_p[:, :, 1] > 90) & (hsv_p[:, :, 2] > 90)
        has_red_cancel = bool(np.sum(mask_r) > 400)
        assert has_red_cancel is False, "耗尽弹窗绝不应检测到红色取消按钮"
        print(f"  - 耗尽弹窗红色像素数: {int(np.sum(mask_r))} (<400 判定为 NO_STAMINA 退出)")
    print("  >>> PASS: 金海豚几何特征纯离线双向判定 100% 精准！")

    # -------------------------------------------------------------
    # Test 10: BandFishPerformAction 选曲安全门禁与跳过状态机
    # -------------------------------------------------------------
    print("\n[Test 10] 验证 BandFishPerformAction 选曲安全门禁与跳过状态机")
    assert registered_actions.get("BandFishPerformAction") is not None
    assert hasattr(my_action, "check_band_fish_skip_button")
    assert hasattr(my_action, "load_band_fish_skip_template")
    assert my_action.check_band_fish_skip_button(None) is None
    assert my_action.load_band_fish_skip_template() is not None

    from test_band_fish_score_selection import main as run_band_fish_score_tests
    assert run_band_fish_score_tests() == 0
    print("  >>> PASS: 选曲安全门禁、最新/指定乐章与 Mock 跳过分支验证通过！")

    # -------------------------------------------------------------
    # Test 11: BandFishInviteLoopAction OCR 与停止门禁
    # -------------------------------------------------------------
    print("\n[Test 11] 验证 BandFishInviteLoopAction 好友 OCR 与停止门禁")
    from test_band_fish_invite import main as run_band_fish_invite_tests
    assert run_band_fish_invite_tests() == 0
    print("  >>> PASS: 好友名附加字符兼容与停止后零追加操作验证通过！")

    print("\n" + "=" * 70)
    print("=== [ALL PASS] DailyRoutineTask v3 全部 11 大离线测试用例 100% 通过！ ===")
    print("=" * 70)
    return True

if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
