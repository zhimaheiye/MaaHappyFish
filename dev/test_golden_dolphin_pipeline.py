# -*- coding: utf-8 -*-
"""GoldenDolphin Pipeline、奖励优先级与日常收尾路由静态测试。"""
import json
import os
import sys
from types import SimpleNamespace

import cv2
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

    print("\n--- Test 11: 真实未激活启动帧门禁 (无假阳性) ---")
    start_frame = cv2.imread('dev/exploration/golden_dolphin/02_game_start_stage.png')
    assert start_frame is not None, "Missing start frame fixture"
    
    # 模拟 _get_golden_dolphin_templates 的结构
    coin_tpl = templates['activation_coin']
    xp_tpls = rewards['xp']
    heart_tpls = rewards['heart']
    gem_tpls = rewards['gem']
    
    assert _find_golden_dolphin_template_targets(start_frame, coin_tpl), "Must find activation coin in start frame"
    assert not _find_golden_dolphin_xp(start_frame, xp_tpls), "XP false positive on start frame"
    assert not _find_golden_dolphin_template_targets(start_frame, heart_tpls), "Heart false positive on start frame"
    assert not _find_golden_dolphin_template_targets(start_frame, gem_tpls), "Gem false positive on start frame"
    print('[PASS] Check 11: 初始帧只识别到贝币，其余奖励未发生假阳性触发！')

    print("\n--- Test 12: 贝币启动阶段仅限点击1次且必带 wait 契约 ---")
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
        def __init__(self, ctx, frame):
            self.ctx = ctx
            self.frame = frame
            self.click_count = 0
            self.last_job = None
            
        def post_screencap(self):
            class _CapJob:
                def __init__(self, f): self.f = f
                def wait(self): return self
                def get(self): return self.f
            return _CapJob(self.frame)

        def post_click(self, x, y):
            self.click_count += 1
            self.last_job = _StrictFakeJob()
            self.ctx.tasker.stopping = True
            return self.last_job
            
    ctx = _FakeContext()
    ctx.tasker.controller = _StrictFakeController(ctx, start_frame)
    golden_dolphin_state['reward_priority'] = 'xp'
    
    GoldenDolphinPlayGameAction().run(ctx, SimpleNamespace(custom_action_param=""))
    
    assert ctx.tasker.controller.click_count == 1, f"Expected 1 post_click for startup phase, got {ctx.tasker.controller.click_count}"
    assert ctx.tasker.controller.last_job is not None, "post_click was not called"
    assert ctx.tasker.controller.last_job.wait_called, "job.wait() was not called on activation coin"
    print('[PASS] Check 12: 隐藏启动阶段精确点击 1 次贝币并调用了 job.wait() 同步等待！')

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
