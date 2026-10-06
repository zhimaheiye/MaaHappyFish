#!/usr/bin/env python3
"""2026-10-01/02 台式机报告：入口中心、留言箱导航、幸运时刻关闭离线验证。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import my_action
from maa.define import Rect


def load(name):
    return json.loads((ROOT / 'assets/resource/pipeline' / name).read_text(encoding='utf-8'))


def test_band_entry_center():
    band = load('features/band_fish.json')
    for name in ('BandFishStartAtAmusementGrid', 'BandFishEnterFromGrid', 'BandFishStartAtTank'):
        assert band[name]['custom_action'] == 'ClickRecognizedCenterAction'
        assert band[name]['on_error'] == ['BandFishNavigationFailed']
    clicks = []
    controller = SimpleNamespace(post_click=lambda x, y: (
        clicks.append((x, y)) or SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=True))
    ))
    tasker = SimpleNamespace(controller=controller, stopping=False, running=True)
    context = SimpleNamespace(tasker=tasker)
    action = my_action.ClickRecognizedCenterAction()
    assert action.run(context, SimpleNamespace(box=Rect(561, 423, 60, 60), custom_action_param='null'))
    assert clicks == [(591, 453)]  # 现场失败落点为 (613,424)，位于圆形按钮边角。
    assert not action.run(context, SimpleNamespace(box=Rect(561, 423, 0, 60), custom_action_param='null'))
    tasker.stopping = True
    assert not action.run(context, SimpleNamespace(box=Rect(561, 423, 60, 60), custom_action_param='null'))
    assert clicks == [(591, 453)]


def test_message_box_bridge():
    common = load('common/common.json')
    bridge = common['FriendPageMessageBoxToStarFriends']
    assert bridge['expected'] == '未读留言最多保留'
    assert bridge['roi'] == [40, 90, 660, 80]
    assert bridge['target'] == [489, 41, 8, 8]
    assert bridge['next'] == ['FriendPageStarFriendsIdentity']
    assert bridge['on_error'] == ['FriendPageNavigationFailed']
    assert common['FriendPageStarFriendsIdentity']['expected'] == '星级好友'
    assert common['FriendPageNavigationFailed']['action'] == 'StopTask'
    handler = '[JumpBack]FriendPageMessageBoxToStarFriends'
    friend = load('features/friend_gem.json')
    assert handler not in friend['FriendGemStartRouter']['next']
    assert '[JumpBack]FriendGemMessageInbox' in friend['FriendGemStartRouter']['next']
    assert 'FriendGemStartRouter' in friend['FriendGemOpenFriendPage']['next']
    manatee = load('features/manatee.json')
    assert handler in manatee['ManateeWeekendGate']['next']
    assert handler not in manatee['ManateeStartRouter']['next']  # 工作日不穿透进入好友页。
    assert handler in manatee['ManateeOpenFriendPage']['next']


def test_lucky_moment_close():
    common = load('common/common.json')
    assert common['GlobalActivityPagePopup']['any_of'][0] == 'GlobalLuckyMomentTitle'
    assert common['GlobalActivityPagePopup']['next'][0] == 'GlobalLuckyMomentClose'
    assert common['GlobalLuckyMomentIdentity']['all_of'] == [
        'GlobalLuckyMomentTitle', 'GlobalLuckyMomentText'
    ]
    assert common['GlobalLuckyMomentClose']['custom_action'] == 'CloseLuckyMomentAction'
    assert common['GlobalLuckyMomentClose']['on_error'] == ['GlobalActivityPopupFailed']

    def run_case(states, *, capture_fail=False, call_fail=False, touch_fail=False, stop=False):
        # (标题存在，正文存在，主鱼缸可见)：必须有正向回缸证据才算关闭。
        clicks = []
        tasker = SimpleNamespace(stopping=stop, running=True)
        def click(x, y):
            clicks.append((x, y))
            return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=not touch_fail))
        tasker.controller = SimpleNamespace(post_click=click)
        frames = iter(range(len(states)))
        def recognize(name, frame):
            if call_fail:
                return None
            title, body, tank = states[frame]
            hit = {'GlobalLuckyMomentTitle': title, 'GlobalLuckyMomentText': body,
                   'GlobalLuckyMomentIdentity': title and body, 'ConfirmMainScreen': tank}[name]
            return SimpleNamespace(hit=hit, box=(440, 0, 400, 110))
        context = SimpleNamespace(tasker=tasker, run_recognition=recognize)
        with patch.object(my_action, '_capture_720p', side_effect=(
                lambda _: None if capture_fail else next(frames))), patch.object(my_action.time, 'sleep'):
            result = my_action.CloseLuckyMomentAction().run(
                context, SimpleNamespace(custom_action_param='null'))
        return result, clicks

    present, closed = (True, True, False), (False, False, True)
    assert run_case([present, closed]) == (True, [(1015, 103)])
    assert run_case([present, present, closed]) == (True, [(1015, 103)] * 2)
    assert run_case([present] * 4) == (False, [(1015, 103)] * 3)
    assert run_case([closed]) == (True, [])
    assert run_case([(False, True, True)]) == (False, [])  # 单帧漏标题不得误报关闭。
    assert run_case([(True, False, False)]) == (False, [])
    assert run_case([(False, False, False)]) == (False, [])
    assert run_case([present], capture_fail=True) == (False, [])
    assert run_case([present], call_fail=True) == (False, [])
    assert run_case([present], stop=True) == (False, [])
    assert run_case([present], touch_fail=True) == (False, [(1015, 103)])


if __name__ == '__main__':
    for name, test in sorted(list(globals().items())):
        if name.startswith('test_'):
            test()
            print(f'[PASS] {name}')
