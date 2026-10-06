"""海星选择喂食弹窗里的金币鱼食，以及深海缸的贝币鱼食。

金币鱼食模板只包含鱼食袋上半部分。袋子下方的红色库存数字会变化，不能进入模板。
三种袋子外形接近，模板匹配会互相高分命中，因此还要用上半部分的颜色确认。

深海缸三袋的外层都是蓝色，不能靠袋身区分。只认加号右边第一格顶上的玫红色字块。
另外两袋不是贝币鱼食，字块对不上或位置不在第一格时不点。
"""

from __future__ import annotations

import os
from typing import Callable, NamedTuple, Optional

import cv2
import numpy as np

SEARCH_ROI = (490, 140, 400, 340)
SHAPE_THRESHOLD = 0.80

TemplateName = str
ColorCheck = Callable[[float, float, float], bool]


class ShellFood(NamedTuple):
    name: str
    template_name: TemplateName
    matches_color: ColorCheck


def _cheap_color(blue: float, green: float, red: float) -> bool:
    return green > red + 25 and green > blue + 20


def _normal_color(blue: float, green: float, red: float) -> bool:
    return red > 200 and green > 180 and blue > 140 and (red - green) < 45 and (green - blue) > 20


def _high_color(blue: float, green: float, red: float) -> bool:
    return red > 200 and 145 <= green <= 180 and blue > 130 and (red - green) > 45


SHELL_FOODS = (
    ShellFood("廉价鱼食", "喂食_廉价鱼食.png", _cheap_color),
    ShellFood("普通鱼食", "喂食_普通鱼食.png", _normal_color),
    ShellFood("高级鱼食", "喂食_高级鱼食.png", _high_color),
)

DEEP_SEA_TEMPLATE = "喂食_深海鱼食.png"
PLUS_TEMPLATE = "海星_加号.png"
# 2026-10-06 乖海星弹窗：加号中心 (549, 249)，玫红字块中心 (681, 227)。
# 第二格大约再往右 120 像素，不在这个窗口里。
FIRST_SLOT_DX = (40, 200)
FIRST_SLOT_DY = 70


def _image_dirs() -> list[str]:
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.join(agent_dir, "../resource/image"),
        os.path.join(agent_dir, "../assets/resource/image"),
        os.path.join(agent_dir, "../../assets/resource/image"),
        os.path.abspath("assets/resource/image"),
        os.path.abspath("client_avalonia/resource/image"),
        os.path.abspath("resource/image"),
    ]


def load_food_template(template_name: str) -> Optional[np.ndarray]:
    for directory in _image_dirs():
        path = os.path.abspath(os.path.join(directory, template_name))
        if not os.path.isfile(path):
            continue
        template = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if template is not None and template.size > 0:
            return template
    return None


def _search_view(image: np.ndarray) -> Optional[tuple[np.ndarray, int, int]]:
    if image is None or getattr(image, "size", 0) == 0 or image.ndim != 3:
        return None
    height, width = image.shape[:2]
    x, y, roi_w, roi_h = SEARCH_ROI
    x2 = min(width, x + roi_w)
    y2 = min(height, y + roi_h)
    if x2 <= x or y2 <= y:
        return None
    return image[y:y2, x:x2], x, y


def _rose_label(patch: np.ndarray) -> bool:
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    rose = ((hue > 150) | (hue < 12)) & (sat > 70) & (val > 100)
    if int(rose.sum()) < 80:
        return False
    blue, green, red = (float(value) for value in patch[rose].mean(axis=0))
    return red > 200 and red > green + 80 and blue > green + 20


def _plus_center(search: np.ndarray) -> Optional[tuple[int, int]]:
    template = load_food_template(PLUS_TEMPLATE)
    if template is None:
        return None
    tpl_h, tpl_w = template.shape[:2]
    if search.shape[0] < tpl_h or search.shape[1] < tpl_w:
        return None
    _min_score, score, _min_loc, loc = cv2.minMaxLoc(
        cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    )
    if float(score) < SHAPE_THRESHOLD:
        return None
    return int(loc[0]) + tpl_w // 2, int(loc[1]) + tpl_h // 2


def _is_first_slot(box: tuple[int, int, int, int], plus_center: tuple[int, int]) -> bool:
    x, y, width, height = box
    center_x = x + width / 2
    center_y = y + height / 2
    plus_x, plus_y = plus_center
    dx_min, dx_max = FIRST_SLOT_DX
    return (plus_x + dx_min) < center_x < (plus_x + dx_max) and abs(center_y - plus_y) < FIRST_SLOT_DY


def _pick_deep_sea_food(search: np.ndarray, origin_x: int, origin_y: int) -> Optional[tuple[str, tuple[int, int, int, int]]]:
    plus_center = _plus_center(search)
    template = load_food_template(DEEP_SEA_TEMPLATE)
    if plus_center is None or template is None:
        return None
    tpl_h, tpl_w = template.shape[:2]
    if search.shape[0] < tpl_h or search.shape[1] < tpl_w:
        return None
    scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    masked = scores.copy()
    for _ in range(8):
        _min_score, score, _min_loc, loc = cv2.minMaxLoc(masked)
        if float(score) < SHAPE_THRESHOLD:
            break
        peak_x, peak_y = int(loc[0]), int(loc[1])
        patch = search[peak_y:peak_y + tpl_h, peak_x:peak_x + tpl_w]
        box = (peak_x, peak_y, tpl_w, tpl_h)
        if _rose_label(patch) and _is_first_slot(box, plus_center):
            return "深海鱼食", (origin_x + peak_x, origin_y + peak_y, tpl_w, tpl_h)
        y0 = max(0, peak_y - 8)
        x0 = max(0, peak_x - 8)
        masked[y0:peak_y + 8, x0:peak_x + 8] = 0
    return None


def pick_starfish_food(image: np.ndarray) -> Optional[tuple[str, tuple[int, int, int, int]]]:
    """先认廉价、普通、高级。都没有时，再认加号右边第一格的深海玫红字块。"""
    view = _search_view(image)
    if view is None:
        return None
    search, origin_x, origin_y = view

    for food in SHELL_FOODS:
        template = load_food_template(food.template_name)
        if template is None:
            continue
        tpl_h, tpl_w = template.shape[:2]
        if search.shape[0] < tpl_h or search.shape[1] < tpl_w:
            continue
        scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        masked = scores.copy()
        for _ in range(8):
            _min_score, score, _min_loc, loc = cv2.minMaxLoc(masked)
            if float(score) < SHAPE_THRESHOLD:
                break
            peak_x, peak_y = int(loc[0]), int(loc[1])
            patch = search[peak_y:peak_y + tpl_h, peak_x:peak_x + tpl_w]
            blue, green, red = (float(value) for value in patch.mean(axis=(0, 1)))
            if food.matches_color(blue, green, red):
                return food.name, (origin_x + peak_x, origin_y + peak_y, tpl_w, tpl_h)
            y0 = max(0, peak_y - 8)
            x0 = max(0, peak_x - 8)
            masked[y0:peak_y + 8, x0:peak_x + 8] = 0
    return _pick_deep_sea_food(search, origin_x, origin_y)
