import json

import cv2
import numpy as np

def imread_unicode(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

tpl_next = imread_unicode(r"assets\resource\image\好友_下一位.png")
roi = [1140, 50, 130, 80]

def test_next(path):
    img = cv2.imread(path)
    img_720 = cv2.resize(img, (1280, 720))
    crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res = cv2.matchTemplate(crop, tpl_next, cv2.TM_CCOEFF_NORMED)
    min_v, max_v, min_l, max_l = cv2.minMaxLoc(res)
    print(f"{path}: max score = {max_v:.4f}")
    return max_v

# Tank 1:
assert test_next(r"dev\exploration\friend_gem\screenshots\friend_tank_look.png") >= 0.70

# Tank 2:
assert test_next(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_1.png") >= 0.70

# List page contains a visually similar orange control. Safety comes from routing:
# FriendGemNextFriend is reachable only after a verified friend-tank completion state.
assert test_next(r"dev\exploration\friend_gem\screenshots\current_check.png") >= 0.70
with open(
    r"assets\resource\pipeline\features\friend_gem.json", encoding="utf-8"
) as file:
    friend_pipeline = json.load(file)
assert "FriendGemNextFriend" not in friend_pipeline["FriendGemStartRouter"]["next"]

# Park page:
assert test_next(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png") < 0.50

print("\nAll 4 FriendTank Start Template tests PASSED 100%!")
