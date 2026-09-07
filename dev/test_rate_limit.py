import time, numpy as np
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType
from typing import Optional

Toolkit.init_option("./")
adb = r"D:\Program Files\Netease\MuMu\nx_main\adb.exe"
device = "127.0.0.1:16384"

class FastRateLimitReco(CustomRecognition):
    def __init__(self, target_samples=30):
        super().__init__()
        self.target_samples = target_samples
        self.timestamps = []
        self.prev_time = None

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        now = time.perf_counter()
        if self.prev_time is not None:
            self.timestamps.append((now - self.prev_time) * 1000.0)
        self.prev_time = now
        if len(self.timestamps) >= self.target_samples:
            return (0, 0, 10, 10)
        return None

ctrl = AdbController(adb, device)
ctrl.post_connection().wait()

res = Resource()
reco = FastRateLimitReco(target_samples=30)
res.register_custom_recognition("FastRateLimitReco", reco)

pipeline_override = {
    "BenchmarkEntry": {
        "recognition": "Custom",
        "custom_recognition": "FastRateLimitReco",
        "rate_limit": 0,
        "action": "DoNothing",
        "next": [
            "BenchmarkEntry"
        ]
    }
}

tasker = Tasker()
tasker.bind(res, ctrl)

print("Running with rate_limit=0...")
tasker.post_task("BenchmarkEntry", pipeline_override).wait()

dts = np.array(reco.timestamps)
print(f"rate_limit=0 results (30 samples):")
print(f"  Mean   : {np.mean(dts):.2f} ms")
print(f"  Median : {np.median(dts):.2f} ms")
print(f"  P90    : {np.percentile(dts, 90):.2f} ms")
print(f"  P95    : {np.percentile(dts, 95):.2f} ms")
print(f"  Min    : {np.min(dts):.2f} ms")
print(f"  Max    : {np.max(dts):.2f} ms")