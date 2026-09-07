import cv2, sys
from rapidocr_onnxruntime import RapidOCR

img2 = cv2.imread(r"dev\exploration\friend_gem\screenshots\user_fish_baby_park_2.png")
img_720 = cv2.resize(img2, (1280, 720))

roi = [400, 5, 480, 140]
crop = img_720[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]

ocr = RapidOCR()
results, _ = ocr(crop)
for bbox, text, score in (results or []):
    sys.stdout.buffer.write(f"crop text: '{text}', score: {float(score):.3f}\n".encode('utf-8'))