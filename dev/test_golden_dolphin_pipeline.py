# -*- coding: utf-8 -*-
"""GoldenDolphin Pipeline、奖励优先级与日常收尾路由静态测试。"""
import json
import os
import sys
from types import SimpleNamespace

import cv2
import inspect
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.runtime_state import golden_dolphin_state, daily_routine_state
from agent.my_reco import CheckGoldenDolphinCanPlayReco, CheckGoldenDolphinRepeatReco
from agent.my_action import (
    GOLDEN_DOLPHIN_REWARD_ORDER,
    GoldenDolphinInitAction,
    GoldenDolphinNavigationAction,
    GoldenDolphinPlayGameAction,
    GoldenDolphinExitAction,
    GoldenDolphinDoneAction,
    _complete_golden_dolphin_round,
    advance_daily_routine_step,
    _find_golden_dolphin_coin,
    _find_golden_dolphin_template_targets,
    _find_golden_dolphin_activation_coin,
    _find_golden_dolphin_xp,
    _get_golden_dolphin_templates,
    _return_golden_dolphin_to_tank,
    _select_golden_dolphin_frame_targets,
)


def _place_template(canvas, template, left, top):
    height, width = template.shape[:2]
    canvas[top:top + height, left:left + width] = template
    return left + width // 2, top + height // 2


def run_tests():
    print('=' * 65)
    print('  GoldenDolphin Pipeline Topology & Reward Priority Tests')
    print('=' * 65)

    print("\n--- Test 1: Pipeline JSON Topology ---")
    pfile = os.path.join('assets', 'resource', 'pipeline', 'features', 'golden_dolphin.json')
    with open(pfile, 'r', encoding='utf-8') as f:
        pipe = json.load(f)

    expected_nodes = [
        'GoldenDolphinTask',
        'GoldenDolphinNavigation',
        'GoldenDolphinPlayGame',
        'GoldenDolphinExit',
        'GoldenDolphinRepeat',
        'GoldenDolphinDone',
    ]
    for node in expected_nodes:
        assert node in pipe, f'Missing node: {node}'
    business_next = lambda node: [name for name in pipe[node]['next'] if not name.startswith('[JumpBack]Global')]
    assert pipe['GoldenDolphinTask']['custom_action'] == 'GoldenDolphinInitAction'
    assert '任务开始' in pipe['GoldenDolphinTask']['focus']['Node.Action.Succeeded']
    assert business_next('GoldenDolphinTask') == ['GoldenDolphinNavigation']
    assert business_next('GoldenDolphinNavigation') == ['GoldenDolphinPlayGame', 'GoldenDolphinDone']
    assert pipe['GoldenDolphinNavigation']['custom_action'] == 'GoldenDolphinNavigationAction'
    assert pipe['GoldenDolphinPlayGame']['custom_recognition'] == 'CheckGoldenDolphinCanPlayReco'
    assert pipe['GoldenDolphinPlayGame']['custom_action'] == 'GoldenDolphinPlayGameAction'
    assert business_next('GoldenDolphinPlayGame') == ['GoldenDolphinExit']
    assert pipe['GoldenDolphinExit']['custom_action'] == 'GoldenDolphinExitAction'
    assert business_next('GoldenDolphinExit') == ['GoldenDolphinRepeat', 'GoldenDolphinDone']
    assert pipe['GoldenDolphinRepeat']['custom_recognition'] == 'CheckGoldenDolphinRepeatReco'
    assert business_next('GoldenDolphinRepeat') == ['GoldenDolphinNavigation']
    assert pipe['GoldenDolphinDone']['custom_action'] == 'GoldenDolphinDoneAction'
    assert business_next('GoldenDolphinDone') == ['DailyRoutineReturnIfActive', 'DailyRoutineStandaloneDone']
    print('[PASS] Check 1: Pipeline JSON 拓扑节点与路由完全合规！')

    print("\n--- Test 2: CheckGoldenDolphinCanPlayReco 状态分支裁决 ---")
    reco = CheckGoldenDolphinCanPlayReco()
    for status, expected in (
        ('READY_TO_PLAY', (0, 0, 10, 10)),
        ('NO_STAMINA', None),
        ('FAILED', None),
        ('IDLE', None),
    ):
        golden_dolphin_state['status'] = status
        assert reco.analyze(None, None) == expected
    print('[PASS] Check 2: CheckGoldenDolphinCanPlayReco 状态分支判定正确！')

    print("\n--- Test 3: 四类奖励模板完整加载 ---")
    templates = _get_golden_dolphin_templates()
    rewards = templates['rewards']
    assert tuple(rewards) == GOLDEN_DOLPHIN_REWARD_ORDER
    assert {category: len(items) for category, items in rewards.items()} == {
        'xp': 2,
        'heart': 1,
        'gem': 4,
        'coin': 3,
    }
    assert len(templates['activation_coin']) == 1
    assert np.array_equal(templates['activation_coin'][0], rewards['coin'][0])
    print('[PASS] Check 3: 经验星/爱心/宝石/贝币全部模板变体已加载！')

    print("\n--- Test 4: 四类奖励均使用全屏识别 ---")
    for category in ('heart', 'gem', 'coin'):
        template = rewards[category][0]
        height, width = template.shape[:2]
        canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
        expected_centers = [
            _place_template(canvas, template, 2, 2),
            _place_template(canvas, template, 1280 - width - 2, 720 - height - 2),
        ]
        candidates = _find_golden_dolphin_template_targets(canvas, rewards[category])
        for expected_x, expected_y in expected_centers:
            assert any(
                abs(x - expected_x) <= 1 and abs(y - expected_y) <= 1
                for x, y, _ in candidates
            ), f'{category} full-screen match missing at {(expected_x, expected_y)}'

    coin_template = rewards['coin'][0]
    coin_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    expected_coin = _place_template(coin_canvas, coin_template, 320, 5)
    assert _find_golden_dolphin_coin(coin_canvas, rewards['coin'])[:2] == expected_coin
    print('[PASS] Check 4: 爱心、宝石、贝币可在完整 1280×720 画面识别！')

    print("\n--- Test 5: 经验星全屏区域检测回归 ---")
    recorded = cv2.imread("dev/exploration/golden_dolphin/03_middle_falling_dense.png")
    candidates = _find_golden_dolphin_xp(recorded, rewards['xp'])
    assert candidates, "recorded XP frame should contain at least one candidate"
    source_x, source_y, _ = candidates[0]
    for target_y in (100, 620):
        shifted = cv2.warpAffine(
            recorded,
            np.float32([[1, 0, 0], [0, 1, target_y - source_y]]),
            (1280, 720),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        shifted_candidates = _find_golden_dolphin_xp(shifted, rewards['xp'])
        assert any(abs(x - source_x) <= 2 and abs(y - target_y) <= 2 for x, y, _ in shifted_candidates)
    print('[PASS] Check 5: 经验星在完整 1280×720 画面内不受纵向 ROI 限制！')

    print("\n--- Test 6: 可选最高优先级与同帧立即兜底 ---")
    all_rewards = recorded.copy()
    placements = {'heart': (10, 10), 'gem': (900, 20), 'coin': (600, 640)}
    for category, (left, top) in placements.items():
        template = rewards[category][0]
        height, width = template.shape[:2]
        _place_template(all_rewards, template, min(left, 1280 - width), min(top, 720 - height))
    for priority in GOLDEN_DOLPHIN_REWARD_ORDER:
        selected, targets = _select_golden_dolphin_frame_targets(all_rewards, rewards, priority)
        assert selected == priority and targets, f'{priority} should win when selected and visible'

    gem_only = np.zeros((720, 1280, 3), dtype=np.uint8)
    _place_template(gem_only, rewards['gem'][0], 500, 250)
    selected, targets = _select_golden_dolphin_frame_targets(gem_only, rewards, 'xp')
    assert selected == 'gem' and targets, 'missing XP must fall back to another reward in the same call/frame'
    print('[PASS] Check 6: 四类均可设为最高优先级；首选未命中时无 1 秒等待并立即兜底！')

    print("\n--- Test 7: UI 参数与初始化状态 ---")
    interface_paths = [
        os.path.join('assets', 'interface.json'),
        os.path.join('client', 'interface.json'),
        os.path.join('client_avalonia', 'interface.json'),
    ]
    raw_interfaces = [open(path, 'rb').read() for path in interface_paths]
    assert raw_interfaces[0] == raw_interfaces[1] == raw_interfaces[2]
    interface = json.loads(raw_interfaces[0].decode('utf-8'))
    option_name = '金海豚奖励优先级'
    task_by_entry = {task['entry']: task for task in interface['task']}
    assert option_name in task_by_entry['GoldenDolphinTask']['option']
    assert option_name in task_by_entry['DailyRoutineTask']['option']
    option = interface['option'][option_name]
    assert option['default_case'] == '经验星'
    assert {
        case['name']: case['pipeline_override']['GoldenDolphinTask']['custom_action_param']['reward_priority']
        for case in option['cases']
    } == {'经验星': 'xp', '爱心': 'heart', '宝石': 'gem', '贝币': 'coin'}

    GoldenDolphinInitAction().run(None, SimpleNamespace(custom_action_param='{"reward_priority":"gem"}'))
    assert golden_dolphin_state['reward_priority'] == 'gem'
    GoldenDolphinInitAction().run(None, SimpleNamespace(custom_action_param='{"reward_priority":"unknown"}'))
    assert golden_dolphin_state['reward_priority'] == 'xp'
    print('[PASS] Check 7: 独立任务/日常收尾均展示参数，默认经验星且非法值安全回退！')

    print("\n--- Test 8: 连续三局状态与无次数正常调度 ---")
    GoldenDolphinInitAction().run(None, None)
    assert golden_dolphin_state['completed_rounds'] == 0
    assert _complete_golden_dolphin_round() == 'NEXT_ROUND'
    assert _complete_golden_dolphin_round() == 'NEXT_ROUND'
    assert _complete_golden_dolphin_round() == 'DONE'
    assert golden_dolphin_state['completed_rounds'] == 3
    repeat_reco = CheckGoldenDolphinRepeatReco()
    golden_dolphin_state['status'] = 'NEXT_ROUND'
    assert repeat_reco.analyze(None, None) == (0, 0, 10, 10)
    golden_dolphin_state['status'] = 'DONE'
    assert repeat_reco.analyze(None, None) is None

    print("\n--- Test 9: GoldenDolphinDoneAction 调度分离与独立保护 ---")
    daily_routine_state['active'] = False
    daily_routine_state['queue'] = []
    golden_dolphin_state['status'] = 'DONE'
    done_act = GoldenDolphinDoneAction()
    done_act.run(None, None)
    assert not daily_routine_state['queue'], 'Standalone should not advance daily routine'

    daily_routine_state['active'] = True
    daily_routine_state['tasks']['GoldenDolphin'] = {'status': 'IDLE'}
    daily_routine_state['queue'] = ['FISHING']
    golden_dolphin_state['status'] = 'DONE'
    done_act.run(None, None)
    assert daily_routine_state['tasks']['GoldenDolphin']['status'] == 'DONE'
    assert daily_routine_state['step'] == 'FISHING'

    daily_routine_state['tasks']['GoldenDolphin'] = {'status': 'IDLE'}
    daily_routine_state['queue'] = ['FISHING']
    golden_dolphin_state['status'] = 'NO_STAMINA'
    done_act.run(None, None)
    assert daily_routine_state['tasks']['GoldenDolphin']['status'] == 'NO_STAMINA'
    assert daily_routine_state['step'] == 'FISHING'
    print('[PASS] Check 9: 独立运行、日常收尾与无次数路由均正确！')

    print("\n--- Test 10: 结算页归位门禁回归 ---")
    game_ending = cv2.imread('dev/exploration/golden_dolphin/03_game_ending_stage.png')
    game_over = cv2.imread('dev/exploration/golden_dolphin/04_game_over.png')
    main_tank = cv2.imread('dev/exploration/golden_dolphin/05_after_cancel.png')
    assert game_ending is not None and game_over is not None and main_tank is not None

    class _FakeJob:
        def __init__(self, value=None):
            self.value = value

        def wait(self):
            return self

        def get(self):
            return self.value

    class _FakeController:
        def __init__(self):
            self.frames = [game_ending, game_over]
            self.frame_index = 0
            self.clicks = []

        def post_screencap(self):
            frame = self.frames[self.frame_index]
            if self.frame_index < len(self.frames) - 1:
                self.frame_index += 1
            return _FakeJob(frame)

        def post_click(self, x, y):
            self.clicks.append((x, y))
            self.frames = [main_tank]
            self.frame_index = 0
            return _FakeJob()

    fake_ctrl = _FakeController()
    assert _return_golden_dolphin_to_tank(fake_ctrl, templates, timeout=3.0)
    assert fake_ctrl.clicks
    cancel_x, cancel_y = fake_ctrl.clicks[0]
    assert 830 <= cancel_x <= 910 and 550 <= cancel_y <= 600
    print('[PASS] Check 10: 结算按钮出现较晚时会按模板点击，并在主鱼缸门禁通过后才推进！')

    print("\n--- Test 11: activation 专用 helper 硬回归 (v0.5.1~v0.5.5 ROI+最高分语义) ---")
    start_frame = cv2.imread('dev/exploration/golden_dolphin/02_game_start_stage.png')
    mid_frame = cv2.imread('dev/exploration/golden_dolphin/03_middle_falling_dense.png')
    initial_frame = cv2.imread('dev/exploration/golden_dolphin/00_initial_screen.png')
    assert start_frame is not None and mid_frame is not None and initial_frame is not None

    activation_tpl = templates['activation_coin'][0]

    def _legacy_v055_find_coin(frame, template, threshold=0.70):
        """内联复刻 v0.5.1~v0.5.5 的 _find_golden_dolphin_coin，作为历史基准。"""
        if frame.shape[:2] != (720, 1280):
            frame = cv2.resize(frame, (1280, 720))
        roi_top, roi_bottom = 120, 650
        search = frame[roi_top:roi_bottom]
        th, tw = template.shape[:2]
        result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if score < threshold:
            return None
        return (location[0] + tw // 2, roi_top + location[1] + th // 2, float(score))

    def _close(a, b):
        return abs(a[0] - b[0]) <= 2 and abs(a[1] - b[1]) <= 2

    # 02 启动帧：已知历史目标 (862,626) score 约 0.9956
    t02 = _find_golden_dolphin_activation_coin(start_frame, activation_tpl)
    assert t02 is not None, "activation helper must find coin on start frame"
    assert 120 <= t02[1] <= 650, f"activation y must be in legacy ROI, got y={t02[1]}"
    assert _close(t02, (862, 626)), f"02 target mismatch: {t02}"
    assert t02[2] >= 0.99, f"activation score should be >=0.99, got {t02[2]:.4f}"
    legacy02 = _legacy_v055_find_coin(start_frame, activation_tpl)
    assert legacy02 is not None and _close(t02, legacy02), f"02 NEW={t02} vs LEGACY={legacy02}"

    # 03 下落密集帧：历史目标 (1122,384)；明确排除 bottom-most 回归目标 (1169,696)
    t03 = _find_golden_dolphin_activation_coin(mid_frame, activation_tpl)
    assert t03 is not None
    assert 120 <= t03[1] <= 650, f"activation y must be in legacy ROI, got y={t03[1]}"
    assert _close(t03, (1122, 384)), f"03 target mismatch: {t03}"
    assert t03[2] >= 0.99, f"activation score should be >=0.99, got {t03[2]:.4f}"
    assert (t03[0], t03[1]) != (1169, 696), "must not pick the bottom-most regression target"
    legacy03 = _legacy_v055_find_coin(mid_frame, activation_tpl)
    assert legacy03 is not None and _close(t03, legacy03), f"03 NEW={t03} vs LEGACY={legacy03}"

    # 00 负样本：未进入游戏时不得无中生有
    assert _find_golden_dolphin_activation_coin(initial_frame, activation_tpl) is None, (
        "00_initial_screen: activation helper must return None"
    )

    # 职责区分：全屏 multi-target detector 保留给正式阶段（y 降序语义不变）
    formal = _find_golden_dolphin_template_targets(start_frame, templates['activation_coin'])
    assert formal, "formal detector must still work"
    assert all(formal[k][1] >= formal[k + 1][1] for k in range(len(formal) - 1)), (
        "formal detector keeps y-descending semantics (unchanged responsibility)"
    )
    print('[PASS] Check 11: activation helper=ROI(120~650)+最高分；02/03 与 LEGACY 一致；00 负样本 None')

    print("\n--- Test 12: 隐藏启动必须点击 v0.5.x 语义的正确贝币坐标 (862,626) ---")
    class _StrictFakeJob:
        def __init__(self):
            self.wait_called = False
        def wait(self):
            self.wait_called = True
            return self

    class _FakeTasker:
        def __init__(self):
            self.stopping = False
            self.running = True
            self.controller = None

    class _FakeContext:
        def __init__(self):
            self.tasker = _FakeTasker()

    class _StrictFakeController:
        def __init__(self, ctx, frames, stop_after_clicks=1):
            self.ctx = ctx
            self.frames = list(frames) if isinstance(frames, (list, tuple)) else [frames]
            self.frame_idx = 0
            self.clicks = []
            self.last_job = None
            self.stop_after_clicks = stop_after_clicks

        def post_screencap(self):
            class _CapJob:
                def __init__(self, f): self.f = f
                def wait(self): return self
                def get(self): return self.f
            frame = self.frames[min(self.frame_idx, len(self.frames) - 1)]
            self.frame_idx += 1
            return _CapJob(frame)

        def post_click(self, x, y):
            self.clicks.append((x, y))
            self.last_job = _StrictFakeJob()
            self.ctx.tasker.stopping = len(self.clicks) >= self.stop_after_clicks
            return self.last_job

    ctx = _FakeContext()
    ctx.tasker.controller = _StrictFakeController(ctx, start_frame)
    golden_dolphin_state['reward_priority'] = 'xp'

    GoldenDolphinPlayGameAction().run(ctx, SimpleNamespace(custom_action_param=""))

    assert len(ctx.tasker.controller.clicks) == 1, (
        f"Expected 1 post_click for startup phase, got {ctx.tasker.controller.clicks}"
    )
    clicked_x, clicked_y = ctx.tasker.controller.clicks[0]
    assert abs(clicked_x - 862) <= 2 and abs(clicked_y - 626) <= 2, (
        f"production clicked wrong coin target: ({clicked_x},{clicked_y}), legacy=(862,626)"
    )
    assert ctx.tasker.controller.last_job is not None, "post_click was not called"
    assert ctx.tasker.controller.last_job.wait_called, "job.wait() was not called on activation coin"
    print('[PASS] Check 12: 生产首次点击坐标=(862,626) 与 v0.5.x 历史目标一致，且 job.wait() 同步等待！')

    print("\n--- Test 12B: 多帧 fresh-coordinate——第二帧必须重新识别移动后的贝币 ---")
    frame_b = np.roll(start_frame, -60, axis=0)
    # B 帧期望目标 = activation helper 在 B 帧上的最高分 ROI 输出（整帧上移 60px
    # 后，02 帧的全帧最高分候选 (909,694) 同步移动到 (909,634)）
    exp_b = _find_golden_dolphin_activation_coin(frame_b, activation_tpl)
    assert exp_b is not None and 120 <= exp_b[1] <= 650, exp_b
    ctx2 = _FakeContext()
    ctx2.tasker.controller = _StrictFakeController(ctx2, [start_frame, frame_b], stop_after_clicks=2)
    golden_dolphin_state['reward_priority'] = 'xp'

    GoldenDolphinPlayGameAction().run(ctx2, SimpleNamespace(custom_action_param=""))

    clicks = ctx2.tasker.controller.clicks
    assert len(clicks) >= 2, f"should click at least twice (one per frame), got {clicks}"
    assert clicks[0] != clicks[1], f"second frame must not reuse stale coordinates: {clicks[:2]}"
    assert abs(clicks[1][0] - exp_b[0]) <= 2 and abs(clicks[1][1] - exp_b[1]) <= 2, (
        f"second frame should click moved target {exp_b}, got {clicks[1]}"
    )
    print(f'[PASS] Check 12B: click[0]={clicks[0]} -> click[1]={clicks[1]}，每帧重新识别、不缓存旧坐标！')

    print("\n--- Test 12C: 隐藏启动阶段禁止调用 Heart/Gem detector (结构禁令) ---")
    import agent.my_action as gd_module

    calls = {"xp": 0, "activation": 0, "template_targets": 0, "heart_or_gem": 0}
    real_xp = gd_module._find_golden_dolphin_xp
    real_act = gd_module._find_golden_dolphin_activation_coin
    real_tt = gd_module._find_golden_dolphin_template_targets
    heart_tpls = rewards['heart']
    gem_tpls = rewards['gem']

    def _spy_xp(frame, tpls):
        calls["xp"] += 1
        return real_xp(frame, tpls)

    def _spy_act(frame, tpl):
        calls["activation"] += 1
        return real_act(frame, tpl)

    def _spy_tt(frame, tpls):
        calls["template_targets"] += 1
        # 隐藏启动阶段传入 Heart/Gem 模板即违规
        if tpls is heart_tpls or tpls is gem_tpls or \
                (len(tpls) and any(t is ht for t in tpls for ht in (heart_tpls + gem_tpls))):
            calls["heart_or_gem"] += 1
            raise AssertionError("startup gate must not call Heart/Gem detector")
        return real_tt(frame, tpls)

    gd_module._find_golden_dolphin_xp = _spy_xp
    gd_module._find_golden_dolphin_activation_coin = _spy_act
    gd_module._find_golden_dolphin_template_targets = _spy_tt
    try:
        ctx3 = _FakeContext()
        ctx3.tasker.controller = _StrictFakeController(ctx3, start_frame, stop_after_clicks=1)
        golden_dolphin_state['reward_priority'] = 'xp'
        GoldenDolphinPlayGameAction().run(ctx3, SimpleNamespace(custom_action_param=""))
    finally:
        gd_module._find_golden_dolphin_xp = real_xp
        gd_module._find_golden_dolphin_activation_coin = real_act
        gd_module._find_golden_dolphin_template_targets = real_tt

    assert calls["heart_or_gem"] == 0, (
        f"Heart/Gem detector was called {calls['heart_or_gem']} times during startup"
    )
    assert calls["xp"] >= 1, "XP detector must gate the startup phase"
    assert calls["activation"] >= 1, "activation helper must be used for startup coin"
    assert len(ctx3.tasker.controller.clicks) == 1
    assert abs(ctx3.tasker.controller.clicks[0][0] - 862) <= 2
    print('[PASS] Check 12C: 隐藏启动只调用 XP+activation helper，Heart/Gem detector 零调用！')

    print("\n--- Test 12D: XP 出现即触发 active_start，activation helper 不再调用 ---")
    calls2 = {"activation": 0, "xp": 0}

    def _spy_xp2(frame, tpls):
        calls2["xp"] += 1
        return real_xp(frame, tpls)

    def _spy_act2(frame, tpl):
        calls2["activation"] += 1
        return real_act(frame, tpl)

    gd_module._find_golden_dolphin_xp = _spy_xp2
    gd_module._find_golden_dolphin_activation_coin = _spy_act2
    try:
        ctx4 = _FakeContext()
        # 03 帧 XP=True：XP 应直接触发 active_start，不进入 activation 路径
        ctx4.tasker.controller = _StrictFakeController(ctx4, mid_frame, stop_after_clicks=1)
        golden_dolphin_state['reward_priority'] = 'xp'
        GoldenDolphinPlayGameAction().run(ctx4, SimpleNamespace(custom_action_param=""))
    finally:
        gd_module._find_golden_dolphin_xp = real_xp
        gd_module._find_golden_dolphin_activation_coin = real_act

    assert calls2["xp"] >= 1, "XP detector must run to detect activation"
    assert calls2["activation"] == 0, (
        f"XP 已出现时 activation helper 仍被调用 {calls2['activation']} 次"
    )
    assert len(ctx4.tasker.controller.clicks) >= 1, "formal collector should take over"
    print('[PASS] Check 12D: XP 出现直接进入正式阶段，activation helper 零调用！')

    print("\n--- Test 12E: Heart false-positive 防护——XP 缺席时 Heart 不得触发激活 ---")
    # 04_game_over 帧：Heart 模板可命中但 XP=False、coin=None。
    # mock XP detector 恒返回 []（模拟 XP 缺席），Heart/Gem detector 一旦被调用即失败。
    calls3 = {"activation": 0}
    stop_flag = {"stop": False}

    def _mock_xp_none(frame, tpls):
        calls3.setdefault("xp", 0)
        calls3["xp"] += 1
        return []

    def _fail_heart(frame, tpls):
        raise AssertionError("startup gate must not call Heart detector (false-positive guard)")

    def _spy_act3(frame, tpl):
        calls3["activation"] += 1
        if calls3["activation"] >= 3:
            stop_flag["stop"] = True
            ctx5.tasker.stopping = True  # 模拟用户停止，避免 75s 空转
        return real_act(frame, tpl)

    gd_module._find_golden_dolphin_xp = _mock_xp_none
    gd_module._find_golden_dolphin_template_targets = _fail_heart
    gd_module._find_golden_dolphin_activation_coin = _spy_act3
    try:
        ctx5 = _FakeContext()
        over_frame = cv2.imread('dev/exploration/golden_dolphin/04_game_over.png')
        assert over_frame is not None
        ctx5.tasker.controller = _StrictFakeController(ctx5, over_frame, stop_after_clicks=10**9)
        golden_dolphin_state['reward_priority'] = 'xp'
        GoldenDolphinPlayGameAction().run(ctx5, SimpleNamespace(custom_action_param=""))
    finally:
        gd_module._find_golden_dolphin_xp = real_xp
        gd_module._find_golden_dolphin_template_targets = real_tt
        gd_module._find_golden_dolphin_activation_coin = real_act

    assert calls3["activation"] >= 2, "XP 缺席时应持续用 activation helper 找贝币（而非误判激活）"
    assert ctx5.tasker.controller.clicks == [] if hasattr(ctx5.tasker.controller, 'clicks') else True
    assert len(ctx5.tasker.controller.clicks) == 0, (
        "Heart-only 帧上不得点击任何 activation coin（04 帧 coin=None）"
    )
    print('[PASS] Check 12E: Heart 命中 + XP 缺席 → 不触发激活、不点击，持续安全找贝币！')

    print("\n--- Test 12F: 普通确认路径禁止调用 RapidOCR（结构 + 运行时双重验证） ---")
    import agent.my_action as gd_mod

    # 结构断言：rapidocr 导入只允许出现在 _get_golden_dolphin_ocr 内
    fn_src = inspect.getsource(gd_mod._get_golden_dolphin_ocr)
    assert "rapidocr_onnxruntime" in fn_src
    module_src = inspect.getsource(gd_mod)
    ocr_fn_start = module_src.find("def _get_golden_dolphin_ocr")
    before_ocr_fn = module_src[:ocr_fn_start]
    assert "rapidocr_onnxruntime" not in before_ocr_fn.split("class GoldenDolphinTaskAction")[0], (
        "rapidocr 导入必须只在 lazy singleton 内"
    )
    # 确认闭环抽函数源码内不得出现 RapidOCR
    confirm_fn_src = inspect.getsource(gd_mod._confirm_golden_dolphin_dialog_closed)
    assert "RapidOCR" not in confirm_fn_src and "rapidocr" not in confirm_fn_src
    print("[PASS] 结构（12F）：rapidocr 仅存在于 lazy singleton，确认闭环函数零 OCR 依赖")

    class _FC:
        def __init__(self, fs):
            self.frames = list(fs)
            self.idx = 0
            self.clicks = []

        def post_screencap(self):
            f = self.frames[min(self.idx, len(self.frames) - 1)]
            self.idx += 1

            class _J:
                def wait(self):
                    return self

                def get(self):
                    return f

            return _J()

        def post_click(self, x, y):
            self.clicks.append((x, y))

            class _J:
                def wait(self):
                    return self

            return _J()

    popup_frame = cv2.imread('dev/exploration/golden_dolphin/02_confirm_popup.png')
    game_frame = cv2.imread('dev/exploration/golden_dolphin/02_game_start_stage.png')
    assert popup_frame is not None and game_frame is not None
    tpl_confirm = _get_golden_dolphin_templates()["confirm"]

    # 运行时断言：普通确认闭环零 RapidOCR 调用（monkeypatch 即失败）
    orig_get_ocr = gd_mod._get_golden_dolphin_ocr

    def _forbidden_ocr():
        raise AssertionError("normal play popup must not call RapidOCR")

    gd_mod._get_golden_dolphin_ocr = _forbidden_ocr
    try:
        ctrl = _FC([game_frame])
        dialog_closed, bx, by = gd_mod._confirm_golden_dolphin_dialog_closed(
            ctrl, tpl_confirm, popup_frame, 824, 480)
        assert dialog_closed is True
        assert ctrl.clicks == [(824, 480)]
    finally:
        gd_mod._get_golden_dolphin_ocr = orig_get_ocr
    print("[PASS] 运行时（12F）：普通确认闭环零 RapidOCR 调用（monkeypatch 未触发）")

    print("\n--- Test 12G: 疑似耗尽分支才允许 RapidOCR + lazy singleton ---")
    calls = {"construct": 0}

    class _FakeRapidOCR:
        def __init__(self):
            calls["construct"] += 1

        def __call__(self, frame):
            return [(None, "机会已全部用完", None)], None

    fake_mod = type(sys)("rapidocr_onnxruntime_fake")
    fake_mod.RapidOCR = _FakeRapidOCR
    saved_mod = sys.modules.get("rapidocr_onnxruntime")
    sys.modules["rapidocr_onnxruntime"] = fake_mod
    try:
        gd_mod._golden_dolphin_ocr = None  # 重置 singleton
        o1 = gd_mod._get_golden_dolphin_ocr()
        o2 = gd_mod._get_golden_dolphin_ocr()
        assert o1 is o2, "lazy singleton 必须复用同一实例"
        assert calls["construct"] == 1, "RapidOCR 只构造一次"
        print("[PASS] lazy singleton（12G）：RapidOCR 仅首次构造，后续复用实例")
    finally:
        gd_mod._golden_dolphin_ocr = None
        if saved_mod is not None:
            sys.modules["rapidocr_onnxruntime"] = saved_mod
        else:
            sys.modules.pop("rapidocr_onnxruntime", None)

    print("\n--- Test 12H: 普通确认闭环——第一次成功 / fresh 坐标重试 / 三次失败 ---")
    from agent.my_action import _confirm_golden_dolphin_dialog_closed as _confirm_loop

    # 场景 1：第一次点击成功
    ctrl1 = _FC([game_frame])
    closed, bx, by = _confirm_loop(ctrl1, tpl_confirm, popup_frame, 824, 480)
    assert closed is True and ctrl1.clicks == [(824, 480)]
    print("[PASS] 确认闭环场景 1：第一次点击 (824,480) 即关闭，无多余点击")

    # 场景 2：第一次未关，第二次 fresh 坐标成功（保持按钮完整落在安全识别区）
    rolled = np.roll(popup_frame, -40, axis=0)
    ctrl2 = _FC([rolled, game_frame])
    closed, bx, by = _confirm_loop(ctrl2, tpl_confirm, popup_frame, 824, 480)
    assert closed is True
    assert len(ctrl2.clicks) == 2, ctrl2.clicks
    assert ctrl2.clicks[0] == (824, 480)
    assert ctrl2.clicks[1] == (824, 440), f"第二次必须使用 fresh 帧坐标: {ctrl2.clicks[1]}"
    print("[PASS] 确认闭环场景 2：第一次未关 → fresh 坐标 (824,440) 重试成功")

    # 场景 3：三次都失败
    ctrl3 = _FC([popup_frame] * 5)
    closed, bx, by = _confirm_loop(ctrl3, tpl_confirm, popup_frame, 824, 480)
    assert closed is False
    assert len(ctrl3.clicks) == 3, "最多 3 次点击"
    print("[PASS] 确认闭环场景 3：三次点击弹窗仍在 → closed=False（上层 FAILED）")

    # 11:39 防回归契约：confirm 模板分数阈值语义
    res_popup = cv2.matchTemplate(popup_frame, tpl_confirm, cv2.TM_CCOEFF_NORMED)
    score_popup = cv2.minMaxLoc(res_popup)[1]
    res_game = cv2.matchTemplate(game_frame, tpl_confirm, cv2.TM_CCOEFF_NORMED)
    score_game = cv2.minMaxLoc(res_game)[1]
    assert score_popup >= 0.65, f"弹窗帧 confirm 模板必须 >=0.65, got {score_popup:.4f}"
    assert score_game < 0.65, f"游戏帧 confirm 模板必须 <0.65, got {score_game:.4f}"
    print(f"[PASS] 11:39 防回归契约：confirm 模板分数 弹窗={score_popup:.4f} / 游戏={score_game:.4f}（阈值 0.65 有效区分）")

    print("\n--- Test 13: 正式阶段优先填充机制 ---")
    class _MockFind:
        def __init__(self, xp_cnt, heart_cnt, gem_cnt, coin_cnt):
            self.xp = [(1, 1, 0.9)] * xp_cnt
            self.heart = [(2, 2, 0.9)] * heart_cnt
            self.gem = [(3, 3, 0.9)] * gem_cnt
            self.coin = [(4, 4, 0.9)] * coin_cnt

    def _mock_collect(frame, priority, xp_cnt, heart_cnt, gem_cnt, coin_cnt):
        import sys
        if 'agent' not in sys.path:
            sys.path.append('agent')
        import my_action
        old_xp = my_action._find_golden_dolphin_xp
        old_others = my_action._find_golden_dolphin_template_targets
        
        mock_data = _MockFind(xp_cnt, heart_cnt, gem_cnt, coin_cnt)
        
        def mock_xp(f, t): return mock_data.xp
        def mock_others(f, t):
            # Hacky way to guess what's being asked
            # Actually, _collect_golden_dolphin_frame_targets uses keys in reward_templates
            return []
            
        my_action._find_golden_dolphin_xp = mock_xp
        
        # Real mock
        def _mock_others2(f, t):
            if t == "fake_heart": return mock_data.heart
            if t == "fake_gem": return mock_data.gem
            if t == "fake_coin": return mock_data.coin
            return []
        my_action._find_golden_dolphin_template_targets = _mock_others2
        
        fake_rewards = {
            "xp": "fake_xp",
            "heart": "fake_heart",
            "gem": "fake_gem",
            "coin": "fake_coin"
        }
        
        try:
            res = my_action._collect_golden_dolphin_frame_targets(None, fake_rewards, priority, 4)
            return [r[0] for r in res]
        finally:
            my_action._find_golden_dolphin_xp = old_xp
            my_action._find_golden_dolphin_template_targets = old_others

    # Case A
    res_a = _mock_collect(None, "xp", 2, 3, 4, 5)
    assert len(res_a) == 4, f"Case A length {len(res_a)}"
    assert res_a == ["xp", "xp", "heart", "heart"], f"Case A wrong items: {res_a}"
    
    # Case B
    res_b = _mock_collect(None, "xp", 6, 3, 4, 0)
    assert len(res_b) == 4
    assert res_b == ["xp", "xp", "xp", "xp"]
    
    # Case C
    res_c = _mock_collect(None, "xp", 0, 1, 2, 5)
    assert len(res_c) == 4
    assert res_c == ["heart", "gem", "gem", "coin"]
    
    print('[PASS] Check 13: 优先填充机制正确地优先取回目标且补足缺口！')

    print("\nALL GOLDEN DOLPHIN PIPELINE TESTS PASSED 100%!")


if __name__ == '__main__':
    run_tests()
