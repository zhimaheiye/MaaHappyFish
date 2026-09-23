#!/usr/bin/env python3
"""独立乐队鱼等待好友接受：长等待、取消和总期限。"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import my_action
from agent.runtime_state import band_fish_state


def main():
    clock = [100.0]
    sleeps = []
    original_monotonic = my_action.time.monotonic
    original_sleep = my_action.time.sleep

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    my_action.time.monotonic = lambda: clock[0]
    my_action.time.sleep = sleep
    context = SimpleNamespace(tasker=SimpleNamespace(running=True, stopping=False))
    action = my_action.BandFishPendingWaitAction()
    try:
        band_fish_state["pending_since"] = clock[0]
        assert action.run(context, SimpleNamespace(custom_action_param=None)) is True
        assert clock[0] == 160.0
        assert max(sleeps) <= 0.5

        clock[0] = 450.0  # 已等待 5 分 50 秒，只能再等剩余 10 秒。
        assert action.run(context, SimpleNamespace(custom_action_param=None)) is True
        assert clock[0] == 460.0
        assert action.run(context, SimpleNamespace(custom_action_param=None)) is False

        clock[0] = 100.0
        context.tasker.stopping = True
        assert action.run(context, SimpleNamespace(custom_action_param=None)) is False
        assert clock[0] == 100.0
    finally:
        my_action.time.monotonic = original_monotonic
        my_action.time.sleep = original_sleep
        band_fish_state["pending_since"] = None

    print("[PASS] 乐队鱼 PENDING 等待、截止时间和停止响应")


if __name__ == "__main__":
    main()
