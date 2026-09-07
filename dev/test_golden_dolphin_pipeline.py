# -*- coding: utf-8 -*-
"""
GoldenDolphin Pipeline 拓扑与路由状态机测试套件 (Phase 2A-2)
验证:
1. features/golden_dolphin.json 5 个节点结构完整性与连接关系
2. CheckGoldenDolphinCanPlayReco 4 种状态分支断言 (READY_TO_PLAY / NO_STAMINA / FAILED / IDLE)
3. GoldenDolphinDoneAction 独立保护与日常收尾联动推进
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.runtime_state import golden_dolphin_state, daily_routine_state
from agent.my_reco import CheckGoldenDolphinCanPlayReco
from agent.my_action import (
    GoldenDolphinNavigationAction,
    GoldenDolphinPlayGameAction,
    GoldenDolphinExitAction,
    GoldenDolphinDoneAction,
    advance_daily_routine_step,
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
        'GoldenDolphinDone',
    ]
    for n in expected_nodes:
        assert n in pipe, f'Missing node: {n}'
    assert pipe['GoldenDolphinTask']['next'] == ['GoldenDolphinNavigation']
    assert pipe['GoldenDolphinNavigation']['next'] == ['GoldenDolphinPlayGame', 'GoldenDolphinDone']
    assert pipe['GoldenDolphinNavigation']['custom_action'] == 'GoldenDolphinNavigationAction'
    assert pipe['GoldenDolphinPlayGame']['custom_recognition'] == 'CheckGoldenDolphinCanPlayReco'
    assert pipe['GoldenDolphinPlayGame']['custom_action'] == 'GoldenDolphinPlayGameAction'
    assert pipe['GoldenDolphinPlayGame']['next'] == ['GoldenDolphinExit']
    assert pipe['GoldenDolphinExit']['custom_action'] == 'GoldenDolphinExitAction'
    assert pipe['GoldenDolphinExit']['next'] == ['GoldenDolphinDone']
    assert pipe['GoldenDolphinDone']['custom_action'] == 'GoldenDolphinDoneAction'
    assert pipe['GoldenDolphinDone']['next'] == ['DailyRoutineDispatcher']
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

    print("\n--- Test 3: GoldenDolphinDoneAction 调度分离与独立保护 ---")
    # 3.1 独立运行 (active=False)
    daily_routine_state['active'] = False
    daily_routine_state['queue'] = []
    golden_dolphin_state['status'] = 'DONE'
    done_act = GoldenDolphinDoneAction()
    done_act.run(None, None)
    assert len(daily_routine_state['queue']) == 0, 'Standalone should not advance daily routine'
    print('[PASS] Check 3a: 独立运行保护验证通过：未激活时不触碰日常收尾调度！')

    # 3.2 日常收尾联动 (active=True)
    daily_routine_state['active'] = True
    daily_routine_state['tasks']['GoldenDolphin'] = {'status': 'IDLE'}
    daily_routine_state['queue'] = ['FISHING']
    golden_dolphin_state['status'] = 'DONE'
    done_act.run(None, None)
    assert daily_routine_state['tasks']['GoldenDolphin']['status'] == 'DONE'
    assert daily_routine_state['step'] == 'FISHING'
    print('[PASS] Check 3b: 日常收尾联动验证通过：按序推进至下一任务 FISHING！')

    print("\nALL GOLDEN DOLPHIN PIPELINE TESTS PASSED 100%!")


if __name__ == '__main__':
    run_tests()
