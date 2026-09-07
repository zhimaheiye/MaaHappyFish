import cv2, numpy as np, sys

# 载入算法
from test_detector_bench import detect_bite_color, detect_bite_template

img_seed = cv2.imread(r"dev\exploration\fishing\screenshots\bite_seed_sample_720.png")
roi = [380, 260, 480, 300]

# 提取感叹号局部图
mark_patch = img_seed[395:508, 598:632].copy()
ph, pw = mark_patch.shape[:2]

tests = []

# 1. 平移测试 (在 ROI 内平移到左上、右下等位置)
for dx, dy in [(-80, -50), (80, 50), (-120, 60), (100, -80)]:
    canvas = cv2.imread(r"dev\exploration\fishing\screenshots\05_location_xinghe.png")
    # 贴在 (600+dx, 400+dy)
    tx, ty = 600 + dx, 400 + dy
    canvas[ty:ty+ph, tx:tx+pw] = mark_patch
    tests.append((f"平移 (dx={dx}, dy={dy})", canvas))

# 2. 缩放测试 (0.85x, 0.9x, 1.1x, 1.15x)
for scale in [0.85, 0.90, 1.10, 1.15]:
    canvas = cv2.imread(r"dev\exploration\fishing\screenshots\05_location_xinghe.png")
    scaled_patch = cv2.resize(mark_patch, (int(pw * scale), int(ph * scale)))
    sph, spw = scaled_patch.shape[:2]
    canvas[400:400+sph, 600:600+spw] = scaled_patch
    tests.append((f"尺寸缩放 ({scale:.2f}x)", canvas))

# 3. 亮度变化 (-30%, +30%)
for b_factor in [0.70, 0.85, 1.15, 1.30]:
    canvas = img_seed.copy()
    canvas = np.clip(canvas.astype(np.float32) * b_factor, 0, 255).astype(np.uint8)
    tests.append((f"亮度变化 ({b_factor:.2f}x)", canvas))

# 4. 运动模糊 (Motion blur kernel 5, 9)
for ksize in [5, 9]:
    canvas = img_seed.copy()
    kernel = np.zeros((ksize, ksize))
    kernel[int((ksize-1)/2), :] = np.ones(ksize)
    kernel /= ksize
    blurred = cv2.filter2D(canvas[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]], -1, kernel)
    canvas[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]] = blurred
    tests.append((f"水平运动模糊 (k={ksize})", canvas))

print(f"=== 合成扰动鲁棒性测试 (共 {len(tests)} 组测试) ===")
print(f"{'测试项':<25} | {'Color+Geo Hit':<15} | {'Template Hit':<15} | {'Template Score':<15}")
print("-" * 75)

c_pass = 0
t_pass = 0

for name, test_img in tests:
    c_hit, c_cost, _ = detect_bite_color(test_img)
    t_hit, t_cost, t_det = detect_bite_template(test_img, threshold=0.65)
    
    if c_hit: c_pass += 1
    if t_hit: t_pass += 1
    
    print(f"{name:<25} | {str(c_hit):<15} | {str(t_hit):<15} | {t_det['score']:.4f}")

print("-" * 75)
print(f"Color+Geometry 通过率: {c_pass}/{len(tests)} ({c_pass/len(tests)*100:.1f}%)")
print(f"TemplateMatch  通过率: {t_pass}/{len(tests)} ({t_pass/len(tests)*100:.1f}%)")