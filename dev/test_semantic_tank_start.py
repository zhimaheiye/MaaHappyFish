import cv2, re
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()
roi = [60, 210, 400, 140]
pattern = r"剩余|刷新体力"

scenes = [
    ("好友列表页", r"dev\exploration\friend_gem\screenshots\current_check.png", False),
    ("正常鱼缸 1 (9 剩余)", r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_1.png", True),
    ("正常鱼缸 2 (9 剩余)", r"dev\exploration\friend_gem\screenshots\live_task_state.png", True),
    ("耗尽鱼缸 1 (大章鱼)", r"dev\exploration\friend_gem\screenshots\friend_tank_look.png", True),
    ("NPC 耗尽鱼缸 (NPC章鱼)", r"dev\exploration\friend_gem\screenshots\debug_failed_step2.png", True),
    ("鱼宝乐园", r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png", False),
]

print("=== 测试语义型好友鱼缸识别: ROI [60, 210, 400, 140] ===")
for name, path, expect in scenes:
    img = cv2.imread(path)
    img_720 = cv2.resize(img, (1280, 720))
    crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res, _ = ocr(crop)
    texts = [t for _, t, _ in (res or [])]
    matched = any(re.search(pattern, t) for t in texts)
    print(f"[{name}]")
    print(f"  OCR texts: {texts}")
    print(f"  Matched  : {matched} (Expected: {expect})")
    assert matched == expect, f"Failed for {name}: expected {expect}, got {matched}"

print("\nALL 6 SEMANTIC TESTS PASSED 100%!")