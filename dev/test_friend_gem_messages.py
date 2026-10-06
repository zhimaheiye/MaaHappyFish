#!/usr/bin/env python3
"""好友摸宝留言箱：类别按钮决策与入口契约。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.friend_gem_messages import choose_message_click, default_message_policy
from agent.my_action import (
    FriendGemHandleMessagesAction,
    FriendGemSetMessagePolicyAction,
)
from agent.runtime_state import friend_gem_state


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


LIVE_SYSTEM_ROW = [
    {"text": "系统消息", "box": [112, 195, 126, 43]},
    {"text": "系统通知", "box": [210, 285, 108, 37]},
    {"text": "感谢你参与悬赏任务，请查收您的礼物！", "box": [212, 333, 453, 30]},
    {"text": "2026-10-06 12:10:57", "box": [610, 295, 238, 27]},
    {"text": "查看", "box": [922, 300, 70, 42]},
    {"text": "删除", "box": [1098, 299, 71, 41]},
]


def _policy(**overrides):
    policy = default_message_policy()
    policy.update(overrides)
    return policy


def test_default_skips_live_system_notice():
    assert choose_message_click(LIVE_SYSTEM_ROW, _policy(), set(), set()) is None


def test_system_accept_clicks_view_and_reject_clicks_delete():
    accept = choose_message_click(LIVE_SYSTEM_ROW, _policy(system="accept"), set(), set())
    assert accept["label"] == "查看"
    assert accept["box"] == [922, 300, 70, 42]
    reject = choose_message_click(LIVE_SYSTEM_ROW, _policy(system="reject"), set(), set())
    assert reject["label"] == "删除"
    assert reject["box"] == [1098, 299, 71, 41]


def test_friend_request_only_clicks_the_literal_button():
    row = [
        {"text": "好友申请", "box": [210, 285, 120, 37]},
        {"text": "查看", "box": [922, 300, 70, 42]},
        {"text": "删除", "box": [1098, 299, 71, 41]},
    ]
    assert choose_message_click(row, _policy(friend_request="accept"), set(), set()) is None
    row[1] = {"text": "同意", "box": [922, 300, 70, 42]}
    row[2] = {"text": "拒绝", "box": [1098, 299, 71, 41]}
    chosen = choose_message_click(row, _policy(friend_request="accept"), set(), set())
    assert chosen["label"] == "同意"
    assert chosen["category"] == "friend_request"


def test_pay_words_block_coupon_and_other_rows():
    coupon = [
        {"text": "折扣券即将过期", "box": [210, 285, 180, 37]},
        {"text": "开心宝购买", "box": [360, 333, 120, 30]},
        {"text": "同意", "box": [922, 300, 70, 42]},
    ]
    assert choose_message_click(coupon, _policy(coupon="accept"), set(), set()) is None
    other = [
        {"text": "等级奖励", "box": [210, 285, 120, 37]},
        {"text": "查看", "box": [922, 300, 70, 42]},
    ]
    chosen = choose_message_click(other, _policy(other="accept"), set(), set())
    assert chosen["label"] == "查看"
    paid = [
        {"text": "等级奖励", "box": [210, 285, 120, 37]},
        {"text": "购买VIP", "box": [360, 333, 100, 30]},
        {"text": "查看", "box": [922, 300, 70, 42]},
    ]
    assert choose_message_click(paid, _policy(other="accept"), set(), set()) is None


def test_unopened_category_tab_is_clicked_before_rows():
    items = [
        {"text": "好友申请", "box": [80, 250, 110, 36]},
        {"text": "系统通知", "box": [210, 285, 108, 37]},
        {"text": "查看", "box": [922, 300, 70, 42]},
    ]
    chosen = choose_message_click(items, _policy(friend_request="reject"), set(), set())
    assert chosen["kind"] == "tab"
    assert chosen["label"] == "好友申请"
    again = choose_message_click(items, _policy(friend_request="reject"), {chosen["key"]}, set())
    assert again is None


def test_policy_node_stores_skip_for_unknown_values():
    friend_gem_state["message_policy"] = default_message_policy()
    action = FriendGemSetMessagePolicyAction()
    argv = SimpleNamespace(custom_action_param=json.dumps({
        "category": "baby_visit",
        "policy": "accept",
    }))
    assert action.run(SimpleNamespace(), argv)
    assert friend_gem_state["message_policy"]["baby_visit"] == "accept"
    bad = SimpleNamespace(custom_action_param=json.dumps({
        "category": "coupon",
        "policy": "buy",
    }))
    assert action.run(SimpleNamespace(), bad)
    assert friend_gem_state["message_policy"]["coupon"] == "skip"


def _run_handle(items, policy, pages):
    friend_gem_state["message_policy"] = policy
    clicks = []

    def click(x, y):
        clicks.append((x, y))
        return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=True))

    controller = SimpleNamespace(post_click=click, post_screencap=lambda: None)
    tasker = SimpleNamespace(controller=controller, stopping=False, running=True)
    context = SimpleNamespace(
        tasker=tasker,
        run_recognition=lambda name, frame: SimpleNamespace(all_results=[
            SimpleNamespace(text=item["text"], box=item["box"]) for item in items
        ]),
    )

    def recognize(name, frame):
        hit = pages[name].pop(0)
        return hit

    with patch("agent.my_action._capture_720p", return_value=object()), \
         patch("agent.my_action._recognition_box", side_effect=lambda context, name, frame: recognize(name, frame)), \
         patch("agent.my_action.time.sleep"):
        ok = FriendGemHandleMessagesAction().run(context, SimpleNamespace(custom_action_param="null"))
    return ok, clicks


def test_skip_policy_only_opens_star_friends():
    pages = {
        "FriendGemMessageInbox": [(40, 117, 400, 32), (40, 117, 400, 32)],
        "FriendPageStarFriendsIdentity": [None, (110, 100, 80, 30)],
    }
    ok, clicks = _run_handle(LIVE_SYSTEM_ROW, _policy(), pages)
    assert ok
    assert clicks == [(493, 45)]


def test_accept_clicks_view_then_star_tab():
    pages = {
        "FriendGemMessageInbox": [(40, 117, 400, 32), (40, 117, 400, 32), (40, 117, 400, 32)],
        "FriendPageStarFriendsIdentity": [None, (110, 100, 80, 30)],
    }
    ok, clicks = _run_handle(LIVE_SYSTEM_ROW, _policy(system="accept"), pages)
    assert ok
    assert clicks == [(957, 321), (493, 45)]


def test_leaving_inbox_without_star_list_clicks_nothing():
    pages = {
        "FriendGemMessageInbox": [None],
        "FriendPageStarFriendsIdentity": [None],
    }
    ok, clicks = _run_handle(LIVE_SYSTEM_ROW, _policy(system="accept"), pages)
    assert not ok
    assert clicks == []


def test_pipeline_keeps_manatee_skip_and_routes_friend_gem():
    friend = load("assets/resource/pipeline/features/friend_gem.json")
    common = load("assets/resource/pipeline/common/common.json")
    manatee = load("assets/resource/pipeline/features/manatee.json")
    hangup = load("assets/resource/pipeline/routine/hangup_schedule.json")
    interface = load("assets/interface.json")
    shared = "[JumpBack]FriendPageMessageBoxToStarFriends"
    assert shared not in friend["FriendGemStartRouter"]["next"]
    assert "[JumpBack]FriendGemMessageInbox" in friend["FriendGemStartRouter"]["next"]
    inbox = friend["FriendGemMessageInbox"]
    assert inbox["custom_action"] == "FriendGemHandleMessagesAction"
    assert inbox["next"] == ["FriendPageStarFriendsIdentity"]
    assert inbox["on_error"] == ["FriendPageNavigationFailed"]
    assert "target" not in inbox
    assert friend["FriendGemMessageListOcr"]["expected"] == ".+"
    assert friend["FriendGemTask"]["next"][-1] == "FriendGemMessagePolicySystem"
    assert friend["FriendGemMessagePolicyOther"]["next"] == ["FriendGemStartRouter"]
    for node, category in (
        ("FriendGemMessagePolicySystem", "system"),
        ("FriendGemMessagePolicyFriendRequest", "friend_request"),
        ("FriendGemMessagePolicyBabyVisit", "baby_visit"),
        ("FriendGemMessagePolicyCoupon", "coupon"),
        ("FriendGemMessagePolicyOther", "other"),
    ):
        param = friend[node]["custom_action_param"]
        assert param == {"category": category, "policy": "skip"}
    assert hangup["HangupFriendGemCollectFish"]["next"][-1] == "FriendGemMessagePolicySystem"
    assert hangup["HangupFriendGemPatrol"]["next"][-1] == "FriendGemMessagePolicySystem"
    assert shared in manatee["ManateeWeekendGate"]["next"]
    assert shared in manatee["ManateeOpenFriendPage"]["next"]
    assert common["FriendPageMessageBoxToStarFriends"]["target"] == [489, 41, 8, 8]
    tasks = {task["name"]: task for task in interface["task"]}
    for name in ("好友摸宝", "日常收尾", "收鱼产物", "多鱼缸巡检"):
        assert "好友留言处理" in tasks[name]["option"]
    option = interface["option"]["好友留言处理"]
    assert option["default_case"] == "全部不处理"
    names = [case["name"] for case in option["cases"]]
    assert names == ["全部不处理", "按类别设置"]
    for key in ("留言系统通知", "留言好友申请", "留言鱼宝宝拜访", "留言折扣券", "留言其它消息"):
        child = interface["option"][key]
        assert child["default_case"] == "不处理"
        assert [case["name"] for case in child["cases"]] == ["不处理", "同意", "拒绝"]


if __name__ == "__main__":
    test_default_skips_live_system_notice()
    test_system_accept_clicks_view_and_reject_clicks_delete()
    test_friend_request_only_clicks_the_literal_button()
    test_pay_words_block_coupon_and_other_rows()
    test_unopened_category_tab_is_clicked_before_rows()
    test_policy_node_stores_skip_for_unknown_values()
    test_skip_policy_only_opens_star_friends()
    test_accept_clicks_view_then_star_tab()
    test_leaving_inbox_without_star_list_clicks_nothing()
    test_pipeline_keeps_manatee_skip_and_routes_friend_gem()
    print("friend gem message tests passed")
