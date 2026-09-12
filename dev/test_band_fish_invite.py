#!/usr/bin/env python3
"""乐队鱼好友 OCR 包含匹配与停止响应离线回归。"""

import os
import re
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import my_action
from agent.runtime_state import band_fish_state


class Job:
    def __init__(self, value=None):
        self.value = value

    def wait(self):
        return self

    def get(self):
        return self.value


class OcrContext:
    def __init__(self, text):
        self.text = text
        self.expected = []

    def run_recognition(self, node_name, _frame, pipeline_override=None):
        assert node_name == "BandFishFriendCardTarget"
        expected = pipeline_override[node_name]["expected"]
        self.expected.append(expected)
        item = SimpleNamespace(text=self.text, box=(180, 220, 90, 28))
        hit = re.fullmatch(expected, self.text) is not None
        return SimpleNamespace(
            hit=hit,
            box=item.box if hit else (0, 0, 0, 0),
            all_results=[item],
        )


class StopController:
    def __init__(self):
        self.context = None
        self.clicks = []
        self.swipes = []

    def post_screencap(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        x, y, width, height = my_action.SLOT_INVITE_INFO[1]["roi"]
        frame[y:y + height, x:x + width] = (0, 255, 0)
        return Job(frame)

    def post_click(self, x, y):
        self.clicks.append((x, y))
        self.context.tasker.stopping = True
        return Job()

    def post_swipe(self, *args):
        self.swipes.append(args)
        return Job()


def main():
    # 在线圆点、等级数字等被合并到名字文本框时，仍应命中指定好友。
    ocr_context = OcrContext("●41一只胖梨")
    box, texts = my_action._band_fish_locate_target_card(
        ocr_context,
        np.zeros((720, 1280, 3), dtype=np.uint8),
        "一只胖梨",
    )
    assert box == (180, 220, 90, 28)
    assert texts == ["●41一只胖梨"]
    assert ocr_context.expected == [".*一只胖梨.*"]

    # 台式机发行版日志中目标稳定被识别成“只胖梨”（漏掉首字“一”），
    # 仍应只通过这个已确认的专用别名命中槽位 2，避免首屏误判后下滑。
    missing_first_char_context = OcrContext("只胖梨")
    box, texts = my_action._band_fish_locate_target_card(
        missing_first_char_context,
        np.zeros((720, 1280, 3), dtype=np.uint8),
        "一只胖梨",
    )
    assert box == (180, 220, 90, 28)
    assert texts == ["只胖梨"]
    assert missing_first_char_context.expected == [".*一只胖梨.*", ".*只胖梨.*"]

    # 不继续放宽为只有“胖梨”，避免相似好友名被误邀。
    too_short_context = OcrContext("胖梨")
    box, _ = my_action._band_fish_locate_target_card(
        too_short_context,
        np.zeros((720, 1280, 3), dtype=np.uint8),
        "一只胖梨",
    )
    assert box is None

    # 用户停止后，CustomAction 不得继续截图、滑动、点好友或点确认。
    controller = StopController()
    context = SimpleNamespace(
        tasker=SimpleNamespace(controller=controller, running=True, stopping=False)
    )
    controller.context = context
    band_fish_state["status"] = None
    ok = my_action.BandFishInviteLoopAction().run(
        context,
        SimpleNamespace(custom_action_param=None),
    )
    assert ok is False
    assert controller.clicks == [my_action.SLOT_INVITE_INFO[1]["click"]]
    assert controller.swipes == []
    assert band_fish_state["status"] is None

    print("[PASS] 乐队鱼好友名包含匹配与停止后零追加操作验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
