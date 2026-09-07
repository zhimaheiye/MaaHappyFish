import cv2, sys, re
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()
roi = [110, 100, 200, 55]
pattern = r"星级好友"

def test_crop(img_path):
    img = cv2.imread(img_path)
    img_720 = cv2.resize(img, (1280, 720))
    crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res, _ = ocr(crop)
    texts = [t for _, t, _ in (res or [])]
    match = any(re.search(pattern, t) for t in texts)
    print(f"{img_path}: {texts} -> Match: {match}")
    return match

assert test_crop(r"dev\exploration\friend_gem\screenshots\current_check.png") == True
assert test_crop(r"dev\exploration\friend_gem\screenshots\friend_tank_look.png") == False
assert test_crop(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_1.png") == False
assert test_crop(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png") == False

print("\nStrict star friends OCR cross-test PASSED 100%!")