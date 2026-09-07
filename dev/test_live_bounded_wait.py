import subprocess, time, cv2, numpy as np, re
from rapidocr_onnxruntime import RapidOCR

adb = r"D:\Program Files\Netease\MuMu\nx_main\adb.exe"
device = "127.0.0.1:16384"
ocr = RapidOCR()

def imread_unicode(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

tpl_bubble = imread_unicode(r"assets\resource\image\金币气泡.png")
tpl_next = imread_unicode(r"assets\resource\image\好友_下一位.png")

def tap(x720, y720):
    subprocess.run([adb, "-s", device, "shell", "input", "tap", str(int(x720*1.5)), str(int(y720*1.5))])

def cap():
    raw = subprocess.check_output([adb, "-s", device, "exec-out", "screencap", "-p"])
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    return cv2.resize(img, (1280, 720))

print("=== 开始 FriendGem 真实实机控制流验证 (3 位好友) ===")

# 点击第一位好友卡片进入
print("[实机测试] 点击第 1 位好友卡片进入鱼缸...")
tap(152, 290)
time.sleep(2.0)

for friend_idx in range(1, 4):
    print(f"\n--- 正在处理第 {friend_idx} 位好友 ---")
    attempts = 0
    bubble_miss_count = 0
    max_misses = 8
    max_attempts = 12

    friend_start_time = time.time()
    while True:
        img = cap()

        # 1. 检查鱼宝乐园 (ROI: [380, 0, 520, 150])
        park_crop = img[0:150, 380:900]
        res, _ = ocr(park_crop)
        texts = [t for _, t, _ in (res or [])]
        if any(re.search(r"鱼宝|乐园", t) for t in texts):
            print(f"  [自愈触发] 误入鱼宝乐园 (OCR: {texts}) -> 点击右上角 X [1207, 54] 恢复！")
            tap(1207, 54)
            time.sleep(1.0)
            continue

        # 2. 检查体力耗尽 (ROI: [60, 210, 400, 140])
        ex_crop = img[210:350, 60:460]
        res_ex, _ = ocr(ex_crop)
        ex_texts = [t for _, t, _ in (res_ex or [])]
        if any("刷新体力" in t for t in ex_texts):
            print(f"  [状态判断] 当前好友体力已耗尽 (OCR: {ex_texts}) -> 退出当前好友")
            break

        # 3. 检查尝试上限
        if attempts >= max_attempts:
            print(f"  [状态判断] 气泡尝试已达上限 ({attempts}/{max_attempts}) -> 退出当前好友")
            break

        # 4. 检查产物气泡 (安全 ROI: [230, 140, 820, 470])
        safe_crop = img[140:610, 230:1050]
        match_res = cv2.matchTemplate(safe_crop, tpl_bubble, cv2.TM_CCOEFF_NORMED)
        min_v, max_v, min_l, max_l = cv2.minMaxLoc(match_res)

        if max_v >= 0.75:
            # 命中气泡！
            attempts += 1
            bubble_miss_count = 0  # 归零
            bx = max_l[0] + 230 + tpl_bubble.shape[1] // 2
            by = max_l[1] + 140 + tpl_bubble.shape[0] // 2
            print(f"  [气泡命中] 点击产物气泡 ({attempts}/{max_attempts}) 置信度={max_v:.3f} 坐标=({bx},{by})，连续未命中计数归零")
            tap(bx, by)
            time.sleep(0.5)
            continue

        # 5. 检查连续未发现气泡上限
        if bubble_miss_count >= max_misses:
            print(f"  [兜底触发] 连续 {bubble_miss_count} 次未发现气泡 (耗时 ~{bubble_miss_count*0.6:.1f}s)，判定已无可用气泡 -> 退出当前好友")
            break

        # 6. 单帧未发现气泡 -> 等待并累加 miss_count
        bubble_miss_count += 1
        print(f"  [单帧漏检] 暂未发现气泡 ({bubble_miss_count}/{max_misses})，等待 600ms 继续重试...")
        time.sleep(0.6)

    # 切换至下一位好友
    print(f"  [切下一位] 点击右上角 > 切换至下一位好友...")
    tap(1205, 90)
    time.sleep(1.5)

print("\n=== 3 位好友实机控制流验证完成！===")