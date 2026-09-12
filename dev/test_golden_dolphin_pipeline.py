# -*- coding: utf-8 -*-
"""
GoldenDolphin Pipeline 拓扑与路由状态机测试套件 (Phase 2A-2)
验证:
1. features/golden_dolphin.json 6 个节点结构完整性与连接关系
2. CheckGoldenDolphinCanPlayReco 状态分支断言
3. 贝币启动、XP/爱心优先级、连续三局与日常收尾联动推进
"""
import os
import sys
import json

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.runtime_state import golden_dolphin_state, daily_routine_state
from agent.my_reco import CheckGoldenDolphinCanPlayReco, CheckGoldenDolphinRepeatReco
from agent.my_action import (
    GOLDEN_DOLPHIN_HEART_FALLBACK_DELAY_SECONDS,
    GoldenDolphinInitAction,
    GoldenDolphinNavigationAction,
    GoldenDolphinPlayGameAction,
    GoldenDolphinExitAction,
    GoldenDolphinDoneAction,
    _complete_golden_dolphin_round,
    advance_daily_routine_step,
    _find_golden_dolphin_coin,
    _find_golden_dolphin_hearts,
    _find_golden_dolphin_xp,
    _get_golden_dolphin_templates,
    _select_golden_dolphin_frame_targets,
)


def run_tests():
    print('=' * 65)
    print('  GoldenDolphin Pipeline Topology & Routing Test Suite')
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
    for n in expected_nodes:
        assert n in pipe, f'Missing node: {n}'
    business_next = lambda node: [name for name in pipe[node]['next'] if not name.startswith('[JumpBack]Global')]
    assert pipe['GoldenDolphinTask']['custom_action'] == 'GoldenDolphinInitAction'
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
    assert business_next('GoldenDolphinDone') == ['DailyRoutineDispatcher']
    print('[PASS] Check 1: Pipeline JSON 拓扑节点与路由完全合规！')

    print("\n--- Test 2: CheckGoldenDolphinCanPlayReco 状态分支裁决 ---")
    reco = CheckGoldenDolphinCanPlayReco()

    golden_dolphin_state['status'] = 'READY_TO_PLAY'
    res_ready = reco.analyze(None, None)
    assert res_ready == (0, 0, 10, 10), f'READY_TO_PLAY should match: {res_ready}'

    golden_dolphin_state['status'] = 'NO_STAMINA'
    res_no = reco.analyze(None, None)
    assert res_no is None, f'NO_STAMINA should not match: {res_no}'

    golden_dolphin_state['status'] = 'FAILED'
    res_fail = reco.analyze(None, None)
    assert res_fail is None, f'FAILED should not match: {res_fail}'

    golden_dolphin_state['status'] = 'IDLE'
    res_idle = reco.analyze(None, None)
    assert res_idle is None, f'IDLE should not match: {res_idle}'
    print('[PASS] Check 2: CheckGoldenDolphinCanPlayReco 4 种状态分支判定 100% 正确！')

    print("\n--- Test 3: 贝币持续点击与经验阶段切换 ---")
    coin = _get_golden_dolphin_templates()["coin"]
    assert coin is not None and coin.size > 0, "金海豚_贝币.png must load"
    coin_h, coin_w = coin.shape[:2]
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    left, top = 320, 260
    canvas[top:top + coin_h, left:left + coin_w] = coin
    match = _find_golden_dolphin_coin(canvas, coin)
    assert match is not None
    assert match[:2] == (left + coin_w // 2, top + coin_h // 2)

    stars = _get_golden_dolphin_templates()["stars"]
    assert len(stars) == 2, "金海豚_经验星1.png and 金海豚_经验星2.png must both load"
    heart = _get_golden_dolphin_templates()["heart"]
    assert heart is not None and heart.size > 0, "金海豚_爱心.png must load"
    phase_1, targets_1 = _select_golden_dolphin_frame_targets(canvas, coin, stars, heart, False, 0.0)
    phase_2, targets_2 = _select_golden_dolphin_frame_targets(canvas, coin, stars, heart, False, 0.0)
    assert phase_1 == phase_2 == "coin"
    assert targets_1[0][:2] == targets_2[0][:2] == match[:2]

    phase_after_xp, targets_after_xp = _select_golden_dolphin_frame_targets(canvas, coin, stars, heart, True, 0.0)
    assert phase_after_xp == "wait" and targets_after_xp == []
    assert _find_golden_dolphin_coin(np.zeros_like(canvas), coin) is None
    top_bar = np.zeros_like(canvas)
    top_bar[10:10 + coin_h, left:left + coin_w] = coin
    assert _find_golden_dolphin_coin(top_bar, coin) is None
    print('[PASS] Check 3: XP 出现前可逐帧重复选择贝币；进入 XP 阶段后不再选择贝币！')

    print("\n--- Test 4: 经验区域检测回归 ---")
    recorded = cv2.imread("dev/exploration/golden_dolphin/03_middle_falling_dense.png")
    candidates = _find_golden_dolphin_xp(recorded, stars)
    assert candidates, "recorded XP frame should contain at least one candidate"
    phase_xp, selected_xp = _select_golden_dolphin_frame_targets(recorded, coin, stars, heart, False, 0.0)
    assert phase_xp == "xp" and 1 <= len(selected_xp) <= 4
    source_x, source_y, _ = candidates[0]
    for target_y in (100, 620):
        shifted = cv2.warpAffine(
            recorded,
            np.float32([[1, 0, 0], [0, 1, target_y - source_y]]),
            (1280, 720),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        shifted_candidates = _find_golden_dolphin_xp(shifted, stars)
        assert any(abs(x - source_x) <= 2 and abs(y - target_y) <= 2 for x, y, _ in shifted_candidates)
    print(f'[PASS] Check 4: 经验星在完整 1280×720 画面内不受纵向 ROI 限制！')

    print("\n--- Test 5: XP 优先与全屏爱心补充 ---")
    heart_h, heart_w = heart.shape[:2]
    heart_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    heart_positions = [(7, 5), (1200, 680)]
    for left, top in heart_positions:
        heart_canvas[top:top + heart_h, left:left + heart_w] = heart
    heart_candidates = _find_golden_dolphin_hearts(heart_canvas, heart)
    assert any(abs(x - (7 + heart_w // 2)) <= 1 and abs(y - (5 + heart_h // 2)) <= 1 for x, y, _ in heart_candidates)
    assert any(abs(x - (1200 + heart_w // 2)) <= 1 and abs(y - (680 + heart_h // 2)) <= 1 for x, y, _ in heart_candidates)

    phase_early, targets_early = _select_golden_dolphin_frame_targets(
        heart_canvas, coin, stars, heart, True, GOLDEN_DOLPHIN_HEART_FALLBACK_DELAY_SECONDS - 0.01
    )
    assert phase_early == "wait" and targets_early == []
    phase_heart, targets_heart = _select_golden_dolphin_frame_targets(
        heart_canvas, coin, stars, heart, True, GOLDEN_DOLPHIN_HEART_FALLBACK_DELAY_SECONDS
    )
    assert phase_heart == "heart" and len(targets_heart) == 2

    xp_with_heart = recorded.copy()
    xp_with_heart[5:5 + heart_h, 7:7 + heart_w] = heart
    phase_priority, _ = _select_golden_dolphin_frame_targets(
        xp_with_heart, coin, stars, heart, True, GOLDEN_DOLPHIN_HEART_FALLBACK_DELAY_SECONDS + 1.0
    )
    assert phase_priority == "xp", "经验与爱心同时出现时必须优先经验"
    print('[PASS] Check 5: XP 与爱心均全屏识别；等待阈值后才点爱心，且 XP 始终优先！')

    print("\n--- Test 6: 连续三局状态与无次数正常调度 ---")
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

    print("\n--- Test 7: GoldenDolphinDoneAction 调度分离与独立保护 ---")
    # 7.1 独立运行 (active=False)
    daily_routine_state['active'] = False
    daily_routine_state['queue'] = []
    golden_dolphin_state['status'] = 'DONE'
    done_act = GoldenDolphinDoneAction()
    done_act.run(None, None)
    assert len(daily_routine_state['queue']) == 0, 'Standalone should not advance daily routine'
    print('[PASS] Check 3a: 独立运行保护验证通过：未激活时不触碰日常收尾调度！')

    # 7.2 日常收尾联动 (active=True)
    daily_routine_state['active'] = True
    daily_routine_state['tasks']['GoldenDolphin'] = {'status': 'IDLE'}
    daily_routine_state['queue'] = ['FISHING']
    golden_dolphin_state['status'] = 'DONE'
    done_act.run(None, None)
    assert daily_routine_state['tasks']['GoldenDolphin']['status'] == 'DONE'
    assert daily_routine_state['step'] == 'FISHING'
    print('[PASS] Check 3b: 日常收尾联动验证通过：按序推进至下一任务 FISHING！')

    daily_routine_state['active'] = True
    daily_routine_state['tasks']['GoldenDolphin'] = {'status': 'IDLE'}
    daily_routine_state['queue'] = ['FISHING']
    golden_dolphin_state['status'] = 'NO_STAMINA'
    done_act.run(None, None)
    assert daily_routine_state['tasks']['GoldenDolphin']['status'] == 'NO_STAMINA'
    assert daily_routine_state['step'] == 'FISHING'
    print('[PASS] Check 7c: 无游戏次数按正常业务状态进入下一任务，不作为错误处理！')

    print("\nALL GOLDEN DOLPHIN PIPELINE TESTS PASSED 100%!")


if __name__ == '__main__':
    run_tests()
