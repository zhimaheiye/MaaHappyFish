import time, numpy as np, sys
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
mumu_config = {
    "extras": {
        "mumu": {
            "enable": True,
            "index": 0,
            "path": "D:/Program Files/Netease/MuMu"
        }
    }
}

class FastPipelineReco(CustomRecognition):
    def __init__(self, target_samples=100):
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

ctrl = AdbController(adb, device, screencap_methods=64, input_methods=18446744073709551615, config=mumu_config)
ctrl.post_connection().wait()

res = Resource()
res.post_bundle(r"assets/resource").wait()

reco = FastPipelineReco(target_samples=100)
res.register_custom_recognition("FastPipelineReco", reco)

pipeline_override = {
    "RateLimitFastTest": {
        "recognition": "Custom",
        "custom_recognition": "FastPipelineReco",
        "rate_limit": 10,
        "action": "DoNothing",
        "next": [
            "RateLimitFastTest"
        ]
    }
}

tasker = Tasker()
tasker.bind(res, ctrl)

print("Starting Pipeline test with MuMuPlayerExtras and rate_limit=10 (100 samples)...", flush=True)
job = tasker.post_task("RateLimitFastTest", pipeline_override)
job.wait()

dts = np.array(reco.timestamps)
print(f"Pipeline rate_limit=10 (100 samples):", flush=True)
print(f"  Count  : {len(dts)}", flush=True)
print(f"  Mean   : {np.mean(dts):.2f} ms", flush=True)
print(f"  Median : {np.median(dts):.2f} ms", flush=True)
print(f"  P90    : {np.percentile(dts, 90):.2f} ms", flush=True)
print(f"  P95    : {np.percentile(dts, 95):.2f} ms", flush=True)
print(f"  Min    : {np.min(dts):.2f} ms", flush=True)
print(f"  Max    : {np.max(dts):.2f} ms", flush=True)
print(f"  FPS    : {1000.0 / np.median(dts):.1f} FPS", flush=True)