import cv2, numpy as np, time, glob

# 1. 算法 A: 纯色调/几何形态学检测器 (Color + Geometric Component)
def detect_bite_color(img, roi=[380, 260, 480, 300]):
    t0 = time.perf_counter()
    crop = img[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    
    # 高饱和、高亮度鲜红色
    mask1 = cv2.inRange(hsv, np.array([0, 140, 140]), np.array([10, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([170, 140, 140]), np.array([180, 255, 255]))
    mask = mask1 | mask2
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bars = []
    dots = []
    
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        if area < 30:
            continue
        aspect = h / float(w)
        # 上半部竖条特征: h in [35, 90], w in [10, 35], aspect in [1.8, 5.0]
        if 35 <= h <= 90 and 10 <= w <= 35 and 1.8 <= aspect <= 5.0:
            bars.append((x, y, w, h, area))
        # 下半部方点特征: h in [12, 40], w in [10, 35], aspect in [0.6, 1.6]
        elif 12 <= h <= 40 and 10 <= w <= 35 and 0.6 <= aspect <= 1.6:
            dots.append((x, y, w, h, area))
            
    hit = False
    details = None
    # 严格匹配: 必须有竖条，且竖条下方附近有方点
    for bx, by, bw, bh, barea in bars:
        for dx, dy, dw, dh, darea in dots:
            # 水平中心对齐检查 (误差 <= 15 像素)
            b_cx = bx + bw / 2.0
            d_cx = dx + dw / 2.0
            # 垂直间距检查: 方点在竖条下方，间距 3 到 25 像素
            gap = dy - (by + bh)
            if abs(b_cx - d_cx) <= 15 and 2 <= gap <= 30:
                hit = True
                details = {
                    "bar": (bx + roi[0], by + roi[1], bw, bh),
                    "dot": (dx + roi[0], dy + roi[1], dw, dh),
                    "global_bbox": (bx + roi[0], by + roi[1], max(bw, dw), bh + gap + dh)
                }
                break
        if hit:
            break
            
    cost_ms = (time.perf_counter() - t0) * 1000.0
    return hit, cost_ms, details

# 2. 算法 B: 模板匹配检测器 (TemplateMatch)
tpl_tight = cv2.imread(r"dev\exploration\fishing\screenshots\exclamation_tight.png")
def detect_bite_template(img, roi=[380, 260, 480, 300], threshold=0.75):
    t0 = time.perf_counter()
    crop = img[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
    res = cv2.matchTemplate(crop, tpl_tight, cv2.TM_CCOEFF_NORMED)
    _, max_v, _, max_loc = cv2.minMaxLoc(res)
    hit = max_v >= threshold
    cost_ms = (time.perf_counter() - t0) * 1000.0
    details = {"score": float(max_v), "loc": (max_loc[0] + roi[0], max_loc[1] + roi[1])}
    return hit, cost_ms, details

# 测试集
samples = {
    "咬钩现场 (Positive)": r"dev\exploration\fishing\screenshots\bite_seed_sample_720.png",
    "星河等待 (Negative)": r"dev\exploration\fishing\screenshots\05_location_xinghe.png",
    "冰川等待 (Negative)": r"dev\exploration\fishing\screenshots\07_location_bingchuan.png",
    "宫殿温泉等待 (Negative)": r"dev\exploration\fishing\screenshots\09_location_gongdian.png",
    "大地图页面 (Negative)": r"dev\exploration\fishing\screenshots\04_fishing_location_select.png",
    "主鱼缸页面 (Negative)": r"dev\exploration\fishing\screenshots\01_own_tank.png"
}

print("================================================================================")
print("=== 算法对比测试: Color+Geometry vs TemplateMatch (1280x720, ROI: 480x300) ===")
print("================================================================================")

for name, path in samples.items():
    img = cv2.imread(path)
    if img is None:
        continue
    if img.shape[:2] != (720, 1280):
        img = cv2.resize(img, (1280, 720))
        
    c_hit, c_cost, c_detail = detect_bite_color(img)
    t_hit, t_cost, t_detail = detect_bite_template(img)
    
    print(f"\n样本: [{name}]")
    print(f"  Color+Geometry : hit={c_hit:<5} cost={c_cost:.2f}ms  detail={c_detail}")
    print(f"  TemplateMatch  : hit={t_hit:<5} cost={t_cost:.2f}ms  score={t_detail['score']:.4f}")