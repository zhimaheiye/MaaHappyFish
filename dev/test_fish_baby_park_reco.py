import cv2, json, re
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()
import glob
cfg = None
for pf in glob.glob("assets/resource/pipeline/**/*.json", recursive=True):
    with open(pf, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "FriendGemFishBabyPark" in data:
            cfg = data["FriendGemFishBabyPark"]
            break

roi = cfg["roi"]
expected_pattern = cfg["expected"]

def test_img(path, expect_match):
    img = cv2.imread(path)
    img_720 = cv2.resize(img, (1280, 720))
    crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res, _ = ocr(crop)
    texts = [t for _, t, _ in (res or [])]
    matched = any(re.search(expected_pattern, t) for t in texts)
    print(f"File: {path}")
    print(f"  OCR texts: {texts}")
    print(f"  Matched: {matched} (Expected: {expect_match})")
    assert matched == expect_match, f"Test failed for {path}!"

test_img(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png", True)
test_img(r"dev\exploration\friend_gem\screenshots\friend_tank_look.png", False)
test_img(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_1.png", False)

print("\nAll offline pipeline recognition tests PASSED 100%!")