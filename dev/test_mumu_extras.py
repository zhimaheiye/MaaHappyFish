import time, numpy as np
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.define import MaaAdbScreencapMethodEnum, MaaAdbInputMethodEnum

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

print("Connecting AdbController with MuMuPlayerExtras config...")
ctrl = AdbController(
    adb, 
    device, 
    screencap_methods=64, # MuMuPlayerExtras
    input_methods=18446744073709551615, 
    config=mumu_config
)
ctrl.post_connection().wait()
print("Connected successfully with MuMuPlayerExtras!")

# 1. 连续测试 100 次 controller.post_screencap().wait().get()
print("\n>>> 开始测试 Controller.post_screencap() (MuMuPlayerExtras, 100 次)...")
delays = []
for i in range(100):
    t0 = time.perf_counter()
    im = ctrl.post_screencap().wait().get()
    delays.append((time.perf_counter() - t0) * 1000.0)

dts = np.array(delays)
print(f"MuMuPlayerExtras Screencap (100 次):")
print(f"  Mean   : {np.mean(dts):.2f} ms")
print(f"  Median : {np.median(dts):.2f} ms")
print(f"  P90    : {np.percentile(dts, 90):.2f} ms")
print(f"  P95    : {np.percentile(dts, 95):.2f} ms")
print(f"  Min    : {np.min(dts):.2f} ms")
print(f"  Max    : {np.max(dts):.2f} ms")
print(f"  FPS    : {1000.0 / np.median(dts):.1f} FPS")

# 2. 测试点击速度 (在安全区域点击，例如 (100, 100))
print("\n>>> 开始测试 Controller.post_click() (MuMuPlayerExtras IPC Click, 20 次)...")
click_delays = []
for i in range(20):
    t0 = time.perf_counter()
    ctrl.post_click(100, 100).wait()
    click_delays.append((time.perf_counter() - t0) * 1000.0)

cds = np.array(click_delays)
print(f"MuMuPlayerExtras Click (20 次):")
print(f"  Mean   : {np.mean(cds):.2f} ms")
print(f"  Median : {np.median(cds):.2f} ms")
print(f"  P95    : {np.percentile(cds, 95):.2f} ms")