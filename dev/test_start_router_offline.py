import cv2, json, re
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()

import glob
pipeline = {}
for pf in glob.glob("assets/resource/pipeline/**/*.json", recursive=True):
    with open(pf, "r", encoding="utf-8") as f:
        pipeline.update(json.load(f))

cfg_list = pipeline["FriendGemStartFromFriendList"]
cfg_tank = pipeline["FriendGemStartInFriendTank"]

def match_ocr(img_720, cfg):
    roi = cfg["roi"]
    crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res, _ = ocr(crop)
    texts = [t for _, t, _ in (res or [])]
    matched = any(re.search(cfg["expected"], t) for t in texts)
    return matched, texts

def test_scene(name, path, expected_route):
    img = cv2.imread(path)
    img_720 = cv2.resize(img, (1280, 720))
    m_list, t_list = match_ocr(img_720, cfg_list)
    m_tank, t_tank = match_ocr(img_720, cfg_tank)

    route = None
    if m_list:
        route = "FriendGemStartFromFriendList"
    elif m_tank:
        route = "FriendGemStartInFriendTank"
    else:
        route = "None"

    print(f"[{name}]")
    print(f"  StartFromFriendList: {m_list} ({t_list})")
    print(f"  StartInFriendTank  : {m_tank} ({t_tank})")
    print(f"  Actual Route       : {route} (Expected: {expected_route})")
    assert route == expected_route, f"Failed for {name}: expected {expected_route}, got {route}"

test_scene("好友列表主界面", r"dev\exploration\friend_gem\screenshots\current_check.png", "FriendGemStartFromFriendList")
test_scene("好友鱼缸 1 (NPC大章鱼 0点刷新体力)", r"dev\exploration\friend_gem\screenshots\debug_failed_step2.png", "FriendGemStartInFriendTank")
test_scene("好友鱼缸 2 (大章鱼 0点刷新体力)", r"dev\exploration\friend_gem\screenshots\friend_tank_look.png", "FriendGemStartInFriendTank")
test_scene("好友鱼缸 3 (换缸 9剩余)", r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_1.png", "FriendGemStartInFriendTank")
test_scene("好友鱼缸 4 (兔兔 9剩余)", r"dev\exploration\friend_gem\screenshots\live_task_state.png", "FriendGemStartInFriendTank")
test_scene("鱼宝乐园 (不触发任何启动)", r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png", "None")

print("\nALL 6 SCENARIOS VERIFIED 100% PERFECT WITH PURE SEMANTIC OCR!")