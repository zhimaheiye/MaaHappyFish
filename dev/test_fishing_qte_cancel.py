"""钓鱼咬钩监听必须在任务停止后退出，且不再收杆。"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import my_action
from my_action import FishingCastAndBiteQTEAction, _watch_bite_and_reel, fishing_state


class _Tasker:
    def __init__(self, stopping=False, running=True):
        self.stopping = stopping
        self.running = running
        self.controller = None


class _Context:
    def __init__(self, tasker):
        self.tasker = tasker


class _Job:
    def __init__(self, frame=None):
        self._frame = frame

    def wait(self):
        return self

    def get(self):
        return self._frame


class _ExplodingController:
    def post_screencap(self):
        raise AssertionError("已停止的监听不应再截屏")

    def post_touch_down(self, *args, **kwargs):
        raise AssertionError("已停止的监听不应再收杆")

    def post_touch_up(self, *args, **kwargs):
        raise AssertionError("已停止的监听不应再收杆")


class FishingQteCancelTest(unittest.TestCase):
    def test_stopped_watch_returns_without_touch(self):
        context = _Context(_Tasker(stopping=True, running=True))
        result = _watch_bite_and_reel(
            _ExplodingController(),
            [380, 260, 480, 300],
            1134,
            578,
            30.0,
            0.0,
            context=context,
        )
        self.assertFalse(result)

    def test_stop_after_bite_detected_does_not_reel(self):
        context = _Context(_Tasker(stopping=False, running=True))
        touches = []

        class Controller:
            def post_screencap(self):
                context.tasker.stopping = True
                return _Job(np.zeros((720, 1280, 3), dtype=np.uint8))

            def post_touch_down(self, *args, **kwargs):
                touches.append("down")
                return _Job()

            def post_touch_up(self, *args, **kwargs):
                touches.append("up")
                return _Job()

        original = my_action.detect_bite_color_geo_strict
        my_action.detect_bite_color_geo_strict = lambda crop, early=False: (True, {})
        try:
            result = _watch_bite_and_reel(
                Controller(),
                [380, 260, 480, 300],
                1134,
                578,
                1.0,
                0.0,
                context=context,
            )
        finally:
            my_action.detect_bite_color_geo_strict = original

        self.assertFalse(result)
        self.assertEqual(touches, [])

    def test_stopped_cast_action_does_not_cast(self):
        controller = _ExplodingController()
        tasker = _Tasker(stopping=True, running=True)
        tasker.controller = controller
        fishing_state["cast_count"] = 0
        fishing_state["max_casts"] = 0
        argv = type("Arg", (), {"task_detail": None, "custom_action_param": "null"})()
        result = FishingCastAndBiteQTEAction().run(_Context(tasker), argv)
        self.assertFalse(result)
        self.assertEqual(fishing_state["cast_count"], 0)


if __name__ == "__main__":
    unittest.main()
