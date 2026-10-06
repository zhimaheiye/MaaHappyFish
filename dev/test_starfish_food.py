import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from agent.starfish_food import pick_starfish_food
FIXTURE = os.path.join(ROOT, "dev", "fixtures", "starfish_food_20261006", "feed_popup.png")


def _load():
    image = cv2.imdecode(np.fromfile(FIXTURE, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError(FIXTURE)
    return image


class StarfishFoodTest(unittest.TestCase):
    def test_default_order_picks_cheap_upper_half(self):
        name, box = pick_starfish_food(_load())
        self.assertEqual(name, "廉价鱼食")
        x, y, width, height = box
        self.assertGreater(width, 20)
        self.assertLess(height, 80)
        self.assertLess(y + height, 230)

    def test_falls_through_when_earlier_food_is_absent(self):
        image = _load()
        image[150:230, 620:760] = 0
        name, box = pick_starfish_food(image)
        self.assertEqual(name, "普通鱼食")
        self.assertGreater(box[0], 740)

        image[150:230, 740:900] = 0
        name, _box = pick_starfish_food(image)
        self.assertEqual(name, "高级鱼食")

    def test_other_bags_do_not_count_as_shell_food(self):
        image = _load()
        image[150:250, 500:900] = 0
        image[270:360, 490:620] = 0
        self.assertIsNone(pick_starfish_food(image))


if __name__ == "__main__":
    unittest.main()
