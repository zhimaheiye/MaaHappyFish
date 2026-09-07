import sys

import cv2
import numpy as np


def boxes(path):
    image = cv2.imread(path)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (12, 40, 165), (38, 195, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, (5, 5))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    result = []
    for i in range(1, count):
        x, y, w, h, area = map(int, stats[i])
        if 32 <= w <= 105 and 32 <= h <= 105:
            aspect = w / h
            fill = area / (w * h)
            if 0.60 <= aspect <= 1.70 and 0.38 <= fill <= 0.92 and area >= 1000:
                result.append((x, y, w, h, area, round(fill, 3)))
    return result


for path in sys.argv[1:]:
    print(path, boxes(path))


def feature_boxes(template_paths, paths):
    sift = cv2.SIFT_create()
    descriptors = []
    for template_path in template_paths:
        template = cv2.imread(template_path)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        kp1, desc1 = sift.detectAndCompute(template_gray, None)
        descriptors.append((template_path, template_gray, kp1, desc1))
    for path in paths:
        image = cv2.imread(path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        kp2, desc2 = sift.detectAndCompute(gray, None)
        best = None
        for template_path, template_gray, kp1, desc1 in descriptors:
            matches = cv2.BFMatcher().knnMatch(desc1, desc2, k=2)
            good = [m for m, n in (pair for pair in matches if len(pair) == 2) if m.distance < 0.75 * n.distance]
            if len(good) < 4:
                continue
            src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if matrix is None or inliers is None or int(inliers.sum()) < 4:
                continue
            score = int(inliers.sum())
            if best is None or score > best[0]:
                h, w = template_gray.shape
                corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
                projected = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
                x, y = projected.min(axis=0)
                right, bottom = projected.max(axis=0)
                best = (score, len(good), template_path, [round(x), round(y), round(right - x), round(bottom - y)])
        print(path, best)


if __name__ == "__main__":
    masked = [
        ("debug_frames/f01.png", (1040, 168, 68, 68), "debug_star_masked_1.png"),
        ("debug_frames/f03.png", (1054, 134, 72, 72), "debug_star_masked_3.png"),
        ("debug_frames/f05.png", (955, 78, 68, 68), "debug_star_masked_5.png"),
        ("debug_star_clicked2.png", (978, 238, 67, 67), "debug_star_masked_pose2.png"),
        ("debug_star_clicked3.png", (312, 202, 62, 60), "debug_star_masked_pose3.png"),
    ]
    for src, (x, y, w, h), out in masked:
        crop = cv2.imread(src)[y:y + h, x:x + w]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        raw = cv2.inRange(hsv, (12, 35, 150), (40, 205, 255))
        raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, (7, 7))
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(raw)
        center = np.array([w / 2, h / 2])
        best = None
        best_distance = 10**9
        for i in range(1, count):
            if stats[i, 4] < 100:
                continue
            distance = float(np.linalg.norm(centroids[i] - center))
            if distance < best_distance:
                best_distance = distance
                best = i
        mask = (labels == best).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, (3, 3))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        largest = max(contours, key=cv2.contourArea)
        mask = np.zeros_like(mask)
        cv2.fillPoly(mask, [cv2.convexHull(largest)], 255)
        result = np.full_like(crop, (0, 255, 0))
        result[mask > 0] = crop[mask > 0]
        cv2.imwrite(out, result)
        print(out, best, int(mask.sum() / 255))

    feature_boxes(["debug_star_clean2.png", "debug_star_tpl_1.png", "debug_star_tpl_3.png", "debug_star_tpl_5.png", "debug_star_tpl_pose.png"], sys.argv[1:])
