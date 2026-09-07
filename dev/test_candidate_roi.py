import cv2
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()
roi = [60, 210, 400, 140]

samples = [
    ("大章鱼博士(耗尽)", r"dev/exploration/friend_gem/screenshots/inside_friend1.png", True),
    ("茜茜小公主+0.0s(耗尽)", r"dev/exploration/friend_gem/screenshots/exp_frame_0.0s.png", True),
    ("茜茜小公主+0.3s(耗尽)", r"dev/exploration/friend_gem/screenshots/exp_frame_0.3s.png", True),
    ("茜茜小公主+0.6s(耗尽)", r"dev/exploration/friend_gem/screenshots/exp_frame_0.6s.png", True),
    ("茜茜小公主+1.0s(耗尽)", r"dev/exploration/friend_gem/screenshots/exp_frame_1.0s.png", True),
    ("茜茜小公主+1.5s(耗尽)", r"dev/exploration/friend_gem/screenshots/exp_frame_1.5s.png", True),
    ("茜茜小公主+2.0s(耗尽)", r"dev/exploration/friend_gem/screenshots/exp_frame_2.0s.png", True),
    ("一条咸鱼(未耗尽)", r"dev/exploration/friend_gem/screenshots/repro_screen_init.png", False),
    ("超能小可爱(未耗尽)", r"dev/exploration/friend_gem/screenshots/inside_card11.png", False),
]

all_pass = True
for label, path, expected_exhausted in samples:
    img = cv2.imread(path)
    if img is None:
        print(f"{label}: 文件不存在")
        all_pass = False
        continue
    crop = img[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res, _ = ocr(crop)
    texts = [t for _, t, _ in (res or [])]
    matched = any("刷新体力" in t for t in texts)
    ok = (matched == expected_exhausted)
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"[{label}] texts={texts} | 命中={matched} (预期={expected_exhausted}) -> {status}")

print("Candidate ROI verification:", "ALL PASS!" if all_pass else "SOME FAILED!")