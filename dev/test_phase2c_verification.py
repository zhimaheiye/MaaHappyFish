import sys, os, glob, cv2, time
import numpy as np

# 导入正式模块中刚实现的 detector 与 CustomAction
sys.path.append("agent")
from my_action import detect_bite_color_geo_strict, FishingCastAndBiteQTEAction

roi = [380, 260, 480, 300]

print("================================================================================")
print("=== Phase 2C 零鱼饵严密三层验证 (Replay + 负样本 + Mock控制流) ===")
print("================================================================================")

# ------------------------------------------------------------------------------
# 验证 A: 离线 Replay (Phase 2B 真实捕获的重点帧)
# ------------------------------------------------------------------------------
print("\n[Layer A] Phase 2B 真实咬钩样本序列 Replay 测试:")
bite_dir = "dev/exploration/fishing/phase2b/frames/bite"
crop_files = sorted([f for f in glob.glob(os.path.join(bite_dir, "frame_*.png"))])
print(f"找到 Phase 2B 咬钩时序切片: {len(crop_files)} 帧")

hits_in_replay = []
for fpath in crop_files:
    fname = os.path.basename(fpath)
    crop = cv2.imread(fpath)
    hit, det = detect_bite_color_geo_strict(crop)
    if hit:
        hits_in_replay.append((fname, det))

print(f"正式 detector 在 Phase 2B 序列中检出命中数: {len(hits_in_replay)} 帧")
print(f"首次检出帧: {hits_in_replay[0][0] if hits_in_replay else 'None'}")
for fname, det in hits_in_replay:
    print(f"  命中: {fname}, bar={det['bar']}, dot={det['dot']}")

assert len(hits_in_replay) == 5, f"预期严格命中 5 帧，实际命中 {len(hits_in_replay)} 帧"
assert "0436" in hits_in_replay[0][0], f"预期首命中为 0436，实际为 {hits_in_replay[0][0]}"
print(">>> [Layer A] 离线 Replay 100% 通过！首命中帧严格保持在 #436，无任何行为漂移！")

# ------------------------------------------------------------------------------
# 验证 B: 负样本 Replay (6 大地点静止画面 + 主界面)
# ------------------------------------------------------------------------------
print("\n[Layer B] 负样本静止等待场景 Replay 测试:")
negatives = {
    "星河等待": "dev/exploration/fishing/screenshots/05_location_xinghe.png",
    "冰川等待": "dev/exploration/fishing/screenshots/07_location_bingchuan.png",
    "宫殿温泉等待": "dev/exploration/fishing/screenshots/09_location_gongdian.png",
    "地点选择大地图": "dev/exploration/fishing/screenshots/04_fishing_location_select.png",
    "2x6游乐园面板": "dev/exploration/fishing/screenshots/03_activity_grid.png",
    "自己主鱼缸": "dev/exploration/fishing/screenshots/01_own_tank.png",
    "Pre-cast基线样本": "dev/exploration/fishing/phase2b/frames/pre_cast/pre_00.png"
}

all_neg_pass = True
for name, p in negatives.items():
    if not os.path.exists(p):
        continue
    img = cv2.imread(p)
    if img.shape[:2] == (720, 1280):
        crop = img[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    else:
        crop = img
    hit, det = detect_bite_color_geo_strict(crop)
    early_hit, _ = detect_bite_color_geo_strict(crop, early=True)
    print(f"  负样本 [{name}]: strict={hit}, early={early_hit}")
    if hit or early_hit:
        all_neg_pass = False

assert all_neg_pass, "负样本测试失败，存在误报！"
print(">>> [Layer B] 负样本 Replay 100% 全部通过 (False)，零误报！")

# ------------------------------------------------------------------------------
# 验证 C: Mock Controller 控制流与 One-shot Guard 测试
# ------------------------------------------------------------------------------
print("\n[Layer C] CustomAction 控制流与 One-shot Guard Mock 测试:")

class MockWaitJob:
    def wait(self):
        return self
    def get(self):
        return None

class MockScreencapJob:
    def __init__(self, frame):
        self.frame = frame
    def wait(self):
        return self
    def get(self):
        return self.frame

class MockController:
    def __init__(self, frame_sequence):
        self.frame_sequence = frame_sequence
        self.seq_idx = 0
        self.cast_calls = 0
        self.reel_calls = 0
        self.touch_down_calls = []
        self.touch_up_calls = 0

    def post_touch_down(self, x, y, contact=0, pressure=1):
        self.touch_down_calls.append((x, y))
        return MockWaitJob()

    def post_touch_up(self, contact=0):
        self.touch_up_calls += 1
        return MockWaitJob()

    def post_screencap(self):
        if self.seq_idx < len(self.frame_sequence):
            f = self.frame_sequence[self.seq_idx]
            self.seq_idx += 1
        else:
            f = self.frame_sequence[-1]
        return MockScreencapJob(f)

class MockTasker:
    def __init__(self, controller):
        self.controller = controller

class MockContext:
    def __init__(self, controller):
        self.tasker = MockTasker(controller)

class MockArg:
    def __init__(self, param=""):
        self.custom_action_param = param

normal_full = cv2.imread("dev/exploration/fishing/screenshots/05_location_xinghe.png")
bite_full = cv2.imread("dev/exploration/fishing/phase2b/frames/bite/full_0436_hit.png")

# Case 1: 正常命中序列 (normal -> normal -> bite)
seq_hit = [normal_full, normal_full, bite_full, bite_full]
mock_ctrl1 = MockController(seq_hit)
action1 = FishingCastAndBiteQTEAction()
ctx1 = MockContext(mock_ctrl1)
res1 = action1.run(ctx1, MockArg('{"timeout": 2.0}'))

print(f"Case 1 (正常命中流程):")
print(f"  action 返回: {res1} (预期 True)")
print(f"  Touch down 坐标记录: {mock_ctrl1.touch_down_calls}")
assert res1 is True
# 期望正好下发两次 touch_down: 第一次甩杆 (1134, 578), 第二次收杆 (1134, 578)
assert len(mock_ctrl1.touch_down_calls) == 2, f"预期 2 次 touch_down，实际 {len(mock_ctrl1.touch_down_calls)}"
print("  >>> Case 1 PASS: 甩杆 1 次，收杆 1 次！")

# Case 2: 超时序列 (全部 normal，无 bite)
seq_timeout = [normal_full] * 10
mock_ctrl2 = MockController(seq_timeout)
action2 = FishingCastAndBiteQTEAction()
ctx2 = MockContext(mock_ctrl2)
res2 = action2.run(ctx2, MockArg('{"timeout": 0.2}'))

print(f"\nCase 2 (超时无咬钩流程):")
print(f"  action 返回: {res2} (预期 False)")
print(f"  Touch down 坐标记录: {mock_ctrl2.touch_down_calls}")
assert res2 is False
# 期望仅有 1 次甩杆 touch_down，收杆 0 次，绝无第二杆！
assert len(mock_ctrl2.touch_down_calls) == 1, f"预期 1 次 touch_down，实际 {len(mock_ctrl2.touch_down_calls)}"
print("  >>> Case 2 PASS: 甩杆 1 次，超时安全退出，收杆 0 次，绝无第二杆！")

print("\n================================================================================")
print("=== 全部三层验证 100% 通过！正式实现完全就绪！===")
print("================================================================================")
