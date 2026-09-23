"""鱼宝乐园 V1 的偏好、编号定位与选中态视觉工具。"""

import cv2

PREFERENCES = {"SKIP", "PET", "BASKETBALL", "SING"}
FOOD_PREFERENCES = {"FOOD_BASIC", "FOOD_SUPER", "FOOD_PORCELAIN"}
MILK_PREFERENCES = {"MILK_PINK", "MILK_YELLOW", "MILK_BLUEBERRY"}
PER_BABY = "PER_BABY"


# 2026-09-23 1280×720 实机标定。编号旗会在浮具之间换位，因此先用
# number_1..8 模板识别编号，再把命中点归入最近的固定浮具槽位。
SLOTS = (
    {"flag": (126, 244), "baby": (230, 284), "timer_roi": (150, 365, 160, 45)},
    {"flag": (316, 221), "baby": (410, 190), "timer_roi": (325, 280, 160, 45)},
    {"flag": (522, 263), "baby": (612, 219), "timer_roi": (532, 303, 160, 45)},
    {"flag": (728, 289), "baby": (837, 239), "timer_roi": (747, 323, 160, 45)},
    {"flag": (961, 305), "baby": (1072, 243), "timer_roi": (985, 331, 160, 45)},
    {"flag": (297, 493), "baby": (405, 445), "timer_roi": (322, 524, 160, 45)},
    {"flag": (563, 481), "baby": (678, 405), "timer_roi": (598, 487, 160, 45)},
    {"flag": (858, 566), "baby": (965, 488), "timer_roi": (880, 570, 160, 45)},
)


def make_preferences(default="SKIP"):
    return {number: default for number in range(1, 9)}


def group_preferences(preferences, allowed=PREFERENCES, default="SKIP"):
    groups = {value: [] for value in allowed}
    for number in range(1, 9):
        value = preferences.get(number, default)
        if value not in allowed:
            raise ValueError(f"invalid preference for baby {number}: {value}")
        groups[value].append(number)
    return groups


def resolve_preferences(preferences, uniform, allowed):
    """统一值只在明确选择时覆盖逐只配置。"""
    if uniform == PER_BABY:
        return dict(preferences)
    if uniform not in allowed:
        raise ValueError(f"invalid uniform preference: {uniform}")
    return {number: uniform for number in range(1, 9)}


def build_round_plan(
    play_preferences,
    food_preferences=None,
    milk_preferences=None,
    uniform_preferences=None,
):
    """按鱼食→玩耍→牛奶生成分组批次；玩耍为 SKIP 的宝宝整轮不参与。"""
    food_preferences = food_preferences or make_preferences("FOOD_SUPER")
    milk_preferences = milk_preferences or make_preferences("MILK_BLUEBERRY")
    uniform_preferences = uniform_preferences or {
        "food": PER_BABY,
        "play": PER_BABY,
        "milk": PER_BABY,
    }
    play_preferences = resolve_preferences(
        play_preferences, uniform_preferences.get("play", PER_BABY), PREFERENCES
    )
    food_preferences = resolve_preferences(
        food_preferences, uniform_preferences.get("food", PER_BABY), FOOD_PREFERENCES
    )
    milk_preferences = resolve_preferences(
        milk_preferences, uniform_preferences.get("milk", PER_BABY), MILK_PREFERENCES
    )
    groups = group_preferences(play_preferences)
    targets = sorted(groups["PET"] + groups["BASKETBALL"] + groups["SING"])
    if not targets:
        return []
    food_groups = group_preferences(food_preferences, FOOD_PREFERENCES, "FOOD_SUPER")
    milk_groups = group_preferences(milk_preferences, MILK_PREFERENCES, "MILK_BLUEBERRY")
    plan = [
        (kind, [number for number in food_groups[kind] if number in targets])
        for kind in ("FOOD_BASIC", "FOOD_SUPER", "FOOD_PORCELAIN")
        if any(number in targets for number in food_groups[kind])
    ]
    plan.extend((play, groups[play]) for play in ("PET", "BASKETBALL", "SING") if groups[play])
    plan.extend(
        (kind, [number for number in milk_groups[kind] if number in targets])
        for kind in ("MILK_PINK", "MILK_YELLOW", "MILK_BLUEBERRY")
        if any(number in targets for number in milk_groups[kind])
    )
    return plan


def locate_numbered_babies(frame, templates, threshold=0.82, max_distance=55):
    """把 1~8 数字模板映射到当帧浮具槽位和宝宝点击中心。"""
    if frame is None or frame.shape[:2] != (720, 1280):
        return {}
    located = {}
    used_slots = set()
    for number in range(1, 9):
        template = templates.get(number)
        if template is None or template.size == 0:
            continue
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, top_left = cv2.minMaxLoc(result)
        if score < threshold:
            continue
        hit = (top_left[0], top_left[1])
        distances = [
            (slot_index, (hit[0] - slot["flag"][0]) ** 2 + (hit[1] - slot["flag"][1]) ** 2)
            for slot_index, slot in enumerate(SLOTS)
        ]
        slot_index, distance_sq = min(distances, key=lambda item: item[1])
        if distance_sq > max_distance * max_distance or slot_index in used_slots:
            continue
        used_slots.add(slot_index)
        slot = SLOTS[slot_index]
        located[number] = {
            "slot": slot_index,
            "score": float(score),
            "flag": hit,
            "baby": slot["baby"],
            "timer_roi": slot["timer_roi"],
        }
    return located


def count_completed_hearts(frame, baby_center):
    """统计宝宝左侧本轮已点亮的红心；稳定状态应为 0、2 或 4。"""
    if frame is None or frame.shape[:2] != (720, 1280):
        return -1
    center_x, center_y = baby_center
    x0 = max(0, center_x - 80)
    x1 = min(frame.shape[1], center_x - 25)
    y0 = max(0, center_y - 80)
    y1 = min(frame.shape[0], center_y + 80)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    red = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 160, 180), (10, 255, 255)),
        cv2.inRange(hsv, (170, 160, 180), (179, 255, 255)),
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(red)
    return sum(
        1
        for x, y, width, height, area in stats[1:]
        if 80 <= area <= 600 and 8 <= width <= 35 and 6 <= height <= 22
    )


def has_green_check(frame, baby_center):
    """只在宝宝右下方小范围内确认选中后的绿色对勾。"""
    if frame is None or frame.shape[:2] != (720, 1280):
        return False
    center_x, center_y = baby_center
    x0 = max(0, center_x)
    x1 = min(frame.shape[1], center_x + 75)
    y0 = max(0, center_y - 5)
    y1 = min(frame.shape[0], center_y + 65)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 100, 80), (95, 255, 255))
    _, _, stats, _ = cv2.connectedComponentsWithStats(green)
    return any(
        area >= 120 and width >= 12 and height >= 10
        for x, y, width, height, area in stats[1:]
    )


def classify_sky(frame):
    """1280×720 BGR 帧的顶部中央颜色指纹。"""
    if frame is None or frame.shape[0] != 720 or frame.shape[1] != 1280:
        return "UNKNOWN"
    sample = frame[15:70, 500:780]
    blue = float(sample[:, :, 0].mean())
    red = float(sample[:, :, 2].mean())
    if red > blue:
        return "HOME"
    if blue > red:
        return "MAIN_TANK"
    return "UNKNOWN"
