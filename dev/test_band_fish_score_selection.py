#!/usr/bin/env python3
"""乐队鱼选曲安全门禁离线回归。"""

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import my_action
from agent.runtime_state import band_fish_state


READY_BOX = (572, 608, 130, 45)
TITLE_BOX = (284, 343, 354, 33)
CONFIRM_BOX = (991, 341, 67, 38)
TOP_SCORES = [("欢乐颂", (710, 450, 80, 33)), ("噜啦啦", (712, 595, 77, 29))]
BOTTOM_SCORES = [("美丽的夜空啊", (681, 305, 140, 28)), ("天鹅", (711, 453, 78, 30))]

SCORE_CASES = [
    ("欢乐颂", "欢乐"),
    ("噜啦啦", "噜啦"),
    ("玛丽有只小绵羊", "小绵羊"),
    ("幸福拍手歌", "拍手"),
    ("斗牛士之歌", "斗牛士"),
    ("蓝色多瑙河", "多瑙河"),
    ("铃儿响叮当", "叮当"),
    ("莫扎特40交响曲", "莫扎特"),
    ("小星星", "星星"),
    ("生日歌", "生日"),
    ("新年好", "新年"),
    ("春天在哪里", "春天"),
    ("洋娃娃和小熊跳舞", "小熊"),
    ("孤独的牧羊人", "牧羊人"),
    ("蜗牛与黄鹂鸟", "黄鹂鸟"),
    ("空之精灵", "精灵"),
    ("四小天鹅", "天鹅"),
    ("小燕子", "燕子"),
    ("少女心声", "心声"),
]


class Job:
    def __init__(self, value=None):
        self.value = value

    def wait(self):
        return self

    def get(self):
        return self.value


class FakeController:
    def __init__(self, page="top", highlight=True):
        self.screen = "ready"
        self.page = page
        self.highlight = highlight
        self.selected_box = None
        self.clicks = []
        self.swipes = []
        self.running = True
        self.stopping = False

    def post_click(self, x, y):
        self.clicks.append((x, y))
        if self.screen == "ready":
            self.screen = "dialog"
        elif self.screen == "dialog":
            for _, box in TOP_SCORES + BOTTOM_SCORES:
                bx, by, bw, bh = box
                if (x, y) == (bx + bw // 2, by + bh // 2):
                    self.selected_box = box
                    break
            if (x, y) == (CONFIRM_BOX[0] + CONFIRM_BOX[2] // 2, CONFIRM_BOX[1] + CONFIRM_BOX[3] // 2):
                self.screen = "performance"
        return Job()

    def post_swipe(self, x1, y1, x2, y2, duration):
        self.swipes.append((x1, y1, x2, y2, duration))
        if y2 < y1:
            self.page = "bottom"
        else:
            self.page = "top"
        return Job()

    def post_screencap(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        if self.screen == "dialog":
            # 让上下页在画面差异检测中可区分。
            frame[200:350, 680:830] = (255, 0, 0) if self.page == "top" else (0, 0, 255)
            if self.highlight and self.selected_box is not None:
                bx, by, bw, _ = self.selected_box
                frame[max(0, by - 85):max(0, by - 25), bx + bw + 45:bx + bw + 78] = (0, 200, 255)
        elif self.screen == "performance":
            frame[650:700, 595:685] = (0, 255, 0)
        return Job(frame)


class FakeContext:
    def __init__(self, controller):
        self.tasker = SimpleNamespace(controller=controller, running=True, stopping=False)

    def run_recognition(self, node_name, _frame, pipeline_override=None):
        ctrl = self.tasker.controller
        if node_name == "BandFishCheckReady":
            return _result(ctrl.screen == "ready", READY_BOX)
        if node_name == "BandFishScoreDialogTitle":
            return _result(ctrl.screen == "dialog", TITLE_BOX)
        if node_name == "BandFishScoreConfirm":
            return _result(ctrl.screen == "dialog", CONFIRM_BOX)
        if node_name == "BandFishScoreName":
            items = TOP_SCORES if ctrl.page == "top" else BOTTOM_SCORES
            expected = ((pipeline_override or {}).get(node_name) or {}).get("expected", ".+")
            filtered = [SimpleNamespace(text=text, box=box) for text, box in items if re.fullmatch(expected, text)]
            best = filtered[0] if filtered else None
            return SimpleNamespace(
                hit=bool(filtered),
                box=best.box if best else (0, 0, 0, 0),
                best_result=best,
                all_results=[SimpleNamespace(text=text, box=box) for text, box in items],
                filtered_results=filtered,
            )
        if node_name == "BandFishCheckDone":
            return _result(False, (0, 0, 0, 0))
        return None


class Arg:
    def __init__(self, param):
        self.custom_action_param = json.dumps(param, ensure_ascii=False)


def _result(hit, box):
    return SimpleNamespace(hit=hit, box=box, best_result=None, all_results=[], filtered_results=[])


def _run(param, *, page="top", highlight=True, skip_pos=None):
    ctrl = FakeController(page=page, highlight=highlight)
    ctx = FakeContext(ctrl)
    old_sleep = my_action.time.sleep
    old_skip_check = my_action.check_band_fish_skip_button
    my_action.time.sleep = lambda _seconds: None
    if skip_pos is not None:
        my_action.check_band_fish_skip_button = lambda _frame: skip_pos
    band_fish_state["status"] = "READY_TO_PERFORM"
    band_fish_state["performance_finished"] = False
    try:
        ok = my_action.BandFishPerformAction().run(ctx, Arg(param))
    finally:
        my_action.time.sleep = old_sleep
        my_action.check_band_fish_skip_button = old_skip_check
    return ok, ctrl


def main():
    repo_root = Path(__file__).resolve().parents[1]
    interface_paths = [
        repo_root / "assets" / "interface.json",
        repo_root / "client" / "interface.json",
        repo_root / "client_avalonia" / "interface.json",
    ]
    raw_interfaces = [path.read_bytes() for path in interface_paths]
    assert raw_interfaces[0] == raw_interfaces[1] == raw_interfaces[2]
    interface = json.loads(raw_interfaces[0].decode("utf-8"))
    score_option = interface["option"]["乐队鱼乐章"]
    assert score_option["default_case"] == "最新乐章"
    assert [case["name"] for case in score_option["cases"]] == [
        "最新乐章",
        *[name for name, _ in SCORE_CASES],
    ]
    named_cases = score_option["cases"][1:]
    configured = []
    for case, (name, keyword) in zip(named_cases, SCORE_CASES):
        param = case["pipeline_override"]["BandFishCheckReady"]["custom_action_param"]
        assert param["score_mode"] == "named"
        assert param["score_name"] == name
        assert param.get("score_ocr_keyword", name) == keyword
        configured.append((name, keyword))
    for name, keyword in configured:
        assert [candidate for candidate, _ in configured if keyword in candidate] == [name]
    tasks = {task["entry"]: task for task in interface["task"]}
    assert "乐队鱼乐章" in tasks["BandFishTask"]["option"]
    assert "乐队鱼乐章" in tasks["DailyRoutineTask"]["option"]

    template_path = repo_root / "assets" / "resource" / "image" / "乐队鱼_跳过.png"
    assert template_path.is_file()
    assert my_action.load_band_fish_skip_template() is not None
    assert my_action._BAND_FISH_SKIP_ROI == (1010, 575, 155, 139)

    synthetic_template = np.random.default_rng(42).integers(0, 256, (24, 36, 3), dtype=np.uint8)
    synthetic_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    synthetic_frame[620:644, 1080:1116] = synthetic_template
    old_template_loader = my_action.load_band_fish_skip_template
    my_action.load_band_fish_skip_template = lambda: synthetic_template
    try:
        assert my_action.check_band_fish_skip_button(synthetic_frame) == (1098, 632)
        outside_roi = np.zeros((720, 1280, 3), dtype=np.uint8)
        outside_roi[100:124, 100:136] = synthetic_template
        assert my_action.check_band_fish_skip_button(outside_roi) is None
    finally:
        my_action.load_band_fish_skip_template = old_template_loader

    ok, named = _run(
        {"score_mode": "named", "score_name": "欢乐颂", "score_ocr_keyword": "欢乐"},
        page="bottom",
    )
    assert ok is True
    assert (750, 466) in named.clicks
    assert (1024, 360) in named.clicks
    assert named.clicks.index((750, 466)) < named.clicks.index((1024, 360))

    ok, split_named = _run(
        {
            "score_mode": "named",
            "score_name": "四小天鹅",
            "score_ocr_keyword": "天鹅",
        },
        page="top",
    )
    assert ok is True
    assert (750, 468) in split_named.clicks
    assert any(y1 > y2 for _, y1, _, y2, _ in split_named.swipes)

    ok, latest = _run({"score_mode": "latest"}, page="top")
    assert ok is True
    assert (750, 468) in latest.clicks
    assert latest.page == "bottom"
    assert latest.clicks.index((750, 468)) < latest.clicks.index((1024, 360))

    ok, unsafe = _run({"score_mode": "named", "score_name": "欢乐颂"}, highlight=False)
    assert ok is False
    assert (1024, 360) not in unsafe.clicks, "未确认黄色选中态时严禁点击消耗体力的确定按钮"

    ok, skipped = _run({"score_mode": "named", "score_name": "欢乐颂"}, skip_pos=(1180, 45))
    assert ok is True
    assert (1180, 45) in skipped.clicks

    print("[PASS] 乐队鱼指定/最新乐章选择、确认前安全门禁与跳过分支验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
