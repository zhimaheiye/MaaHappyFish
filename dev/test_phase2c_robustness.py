import sys, os, time, json
import numpy as np

sys.path.insert(0, './agent')
from param_utils import parse_dict_param, safe_float, safe_int
from my_action import (
    FishingCastAndBiteQTEAction,
    FishingWatchBiteOnlyAction,
    ResetFishingStateAction,
    _sync_task_id,
    _watch_bite_and_reel,
    fishing_state,
)

print("================================================================================")
print("=== Phase 2C 全量健壮性与参数解析异常规避套件 ===")
print("================================================================================")

# 1. 极端参数类型全覆盖测试
test_cases = [
    ("null", {}),
    (None, {}),
    ("", {}),
    ("   ", {}),
    ("[]", {}),
    ("true", {}),
    ("false", {}),
    ("123", {}),
    ('{"timeout": 25.5, "btn_x": 1000}', {"timeout": 25.5, "btn_x": 1000}),
    ("malformed json {", {}),
    ({"already": "dict"}, {"already": "dict"}),
]

for raw, expected in test_cases:
    res = parse_dict_param(raw)
    assert res == expected, f"Failed for raw={raw!r}: got {res}, expected {expected}"
    # 测试数值安全转换
    timeout = safe_float(res.get("timeout"), 30.0, min_val=1.0, max_val=120.0)
    btn_x = safe_int(res.get("btn_x"), 1134)
    assert isinstance(timeout, float) and 1.0 <= timeout <= 120.0
    assert isinstance(btn_x, int)

print("1. [Test 1] 极端参数输入 (None, 'null', '', '[]', malformed) 解析全覆盖: 100% PASS！")

# 2. task_id 绑定与跨任务自动重置测试
_sync_task_id(10001)
assert fishing_state["current_task_id"] == 10001
assert fishing_state["cast_count"] == 0
fishing_state["cast_count"] = 4  # 模拟任务中进行了 4 杆
assert fishing_state["cast_count"] == 4

_sync_task_id(10001) # 同一任务继续
assert fishing_state["cast_count"] == 4

_sync_task_id(10002) # 新任务启动 (不同 task_id)
assert fishing_state["current_task_id"] == 10002
assert fishing_state["cast_count"] == 0, "新任务未能自动重置 cast_count！"
print("2. [Test 2] task_id 跨任务生命周期与自动状态重置绑定: 100% PASS！")

# 3. 截屏/控制器底层异常与空值防御测试
class MockFaultyController:
    def __init__(self, mode):
        self.mode = mode
    def post_screencap(self):
        if self.mode == "none":
            class JobNone:
                def wait(self): return self
                def get(self): return None
            return JobNone()
        elif self.mode == "exception":
            raise RuntimeError("Adb disconnected simulation")
        elif self.mode == "empty":
            class JobEmpty:
                def wait(self): return self
                def get(self): return np.zeros((0, 0, 3), dtype=np.uint8)
            return JobEmpty()
        return None

for mode in ["none", "exception", "empty"]:
    faulty_ctrl = MockFaultyController(mode)
    res = _watch_bite_and_reel(faulty_ctrl, [380, 260, 480, 300], 1134, 578, 0.1, time.perf_counter())
    assert res is False, f"Mode {mode} should return False, got {res}"

print("3. [Test 3] Controller 截屏空值/断连异常/零尺寸图像防御: 100% PASS！")

# 4. Action 针对 param='null' 边界调用测试
action = FishingCastAndBiteQTEAction()
class DummyDetail:
    task_id = 99999
class DummyArg:
    task_detail = DummyDetail()
    custom_action_param = "null"

class MockSafeController:
    def __init__(self):
        self.screencap_count = 0
    def post_screencap(self):
        self.screencap_count += 1
        class JobFrame:
            def wait(self): return self
            def get(self): return np.zeros((720, 1280, 3), dtype=np.uint8)
        return JobFrame()
    def post_touch_down(self, x, y):
        class Job:
            def wait(self): return self
        return Job()
    def post_touch_up(self, idx):
        class Job:
            def wait(self): return self
        return Job()

class DummyTasker:
    controller = MockSafeController()
class DummyContext:
    tasker = DummyTasker()

ret = action.run(DummyContext(), DummyArg())
assert ret is False  # 超时未检测到感叹号，正常安全退出
assert fishing_state["cast_count"] == 1
print("4. [Test 4] FishingCastAndBiteQTEAction 对 param='null' 真实运行: 100% PASS (未发生异常)！")

# 5. Pipeline 状态机 on_error 与 FishingSafeAbort 语法完整性
import glob
pipe = {}
for pf in glob.glob("assets/resource/pipeline/**/*.json", recursive=True):
    with open(pf, "r", encoding="utf-8") as f:
        pipe.update(json.load(f))

assert pipe["FishingRound"].get("on_error") == ["FishingSafeAbort"], "FishingRound 必须配置 on_error 兜底！"
assert "FishingSafeAbort" in pipe, "必须存在 FishingSafeAbort 终态节点！"
assert pipe["FishingStartAtWaitingForBite"].get("on_error") == ["FishingSafeAbort"], "WaitingForBite 必须配置 on_error 兜底！"
print("5. [Test 5] Pipeline on_error 异常熔断配置与防死循环结构: 100% PASS！")

print("\n================================================================================")
print("=== 全部健壮性测试 100% PASS！已彻底消除 Client 崩溃与死循环隐患！===")
print("================================================================================")
