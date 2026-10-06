"""海星选择喂食弹窗里的三种金币鱼食。

模板只包含鱼食袋上半部分。袋子下方的红色库存数字会变化，不能进入模板。
三种袋子外形接近，模板匹配会互相高分命中，因此还要用上半部分的颜色确认。
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


def pick_starfish_food(image: np.ndarray) -> Optional[tuple[str, tuple[int, int, int, int]]]:
    """按廉价、普通、高级的顺序返回第一种颜色也相符的上半袋位置。"""
    if image is None or getattr(image, "size", 0) == 0 or image.ndim != 3:
        return None

    height, width = image.shape[:2]
    x, y, roi_w, roi_h = SEARCH_ROI
    x2 = min(width, x + roi_w)
    y2 = min(height, y + roi_h)
    if x2 <= x or y2 <= y:
        return None
    search = image[y:y2, x:x2]

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
                return food.name, (x + peak_x, y + peak_y, tpl_w, tpl_h)
            y0 = max(0, peak_y - 8)
            x0 = max(0, peak_x - 8)
            masked[y0:peak_y + 8, x0:peak_x + 8] = 0
    return None
