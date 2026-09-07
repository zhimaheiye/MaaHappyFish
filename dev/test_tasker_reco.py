from maa.toolkit import Toolkit
from maa.resource import Resource
from maa.controller import AdbController
from maa.tasker import Tasker
import cv2

Toolkit.init_option("./")
res = Resource()
res.post_path("assets/resource").wait()

ctrl = AdbController(
    adb_path=r"D:\Program Files\Netease\MuMu\nx_main\adb.exe",
    address="127.0.0.1:16384",
)
ctrl.post_connection().wait()

tasker = Tasker()
tasker.bind(res, ctrl)

print("Tasker bound successfully!")

# 截取当前屏幕
img = ctrl.post_screencap().get()
print("Screencap obtained:", type(img))

detail = tasker.post_recognition("FriendGemExhausted", img).get()
print("FriendGemExhausted reco result:", detail)
if detail and detail.box:
    print("MATCHED box:", detail.box)
else:
    print("NOT MATCHED")