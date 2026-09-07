import cv2, sys, re
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()
roi = [300, 30, 350, 80]
pattern = r"ID|最近登录"

def test_id(path):
    img = cv2.imread(path)
    img_720 = cv2.resize(img, (1280, 720))
    crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res, _ = ocr(crop)
    texts = [t for _, t, _ in (res or [])]
    matched = any(re.search(pattern, t) for t in texts)
    print(f"{path}: texts={texts} -> Matched: {matched}")
    return matched

print("=== Testing Tank Unique Feature (ID|最近登录) ===")
assert test_id(r"dev\exploration\friend_gem\screenshots\friend_tank_look.png") == True
assert test_id(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_1.png") == True
assert test_id(r"dev\exploration\friend_gem\screenshots\live_task_state.png") == True
assert test_id(r"dev\exploration\friend_gem\screenshots\live_task_state2.png") == True
assert test_id(r"dev\exploration\friend_gem\screenshots\current_check.png") == False
assert test_id(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png") == False

print("\nALL 6 SAMPLES PASSED 100%!")