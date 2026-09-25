"""鱼宝乐园离线契约。"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import cv2

from agent.fish_baby import (
    FOOD_PREFERENCES,
    MILK_PREFERENCES,
    PER_BABY,
    build_round_plan,
    classify_sky,
    count_completed_hearts,
    group_preferences,
    has_green_check,
    locate_numbered_babies,
    make_preferences,
    resolve_preferences,
)


class FishBabyContract(unittest.TestCase):
    def test_color_fingerprint(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[15:70, 500:780, 2] = 180
        self.assertEqual(classify_sky(frame), "HOME")
        frame[15:70, 500:780, 2] = 0
        frame[15:70, 500:780, 0] = 180
        self.assertEqual(classify_sky(frame), "MAIN_TANK")
        self.assertEqual(classify_sky(np.zeros((10, 10, 3), dtype=np.uint8)), "UNKNOWN")

    def test_manual_preferences_and_skip(self):
        values = make_preferences()
        values.update({1: "PET", 2: "SING", 4: "BASKETBALL", 5: "PET", 7: "SING", 8: "PET"})
        food = make_preferences("FOOD_SUPER")
        food.update({1: "FOOD_BASIC", 4: "FOOD_PORCELAIN"})
        milk = make_preferences("MILK_BLUEBERRY")
        milk.update({2: "MILK_PINK", 7: "MILK_YELLOW"})
        groups = group_preferences(values)
        self.assertEqual(groups["PET"], [1, 5, 8])
        self.assertEqual(groups["BASKETBALL"], [4])
        self.assertEqual(groups["SING"], [2, 7])
        self.assertEqual(groups["SKIP"], [3, 6])
        self.assertEqual(set(groups["SKIP"]) & set(groups["PET"] + groups["BASKETBALL"] + groups["SING"]), set())
        self.assertEqual(build_round_plan(values, food, milk), [
            ("FOOD_BASIC", [1]),
            ("FOOD_SUPER", [2, 5, 7, 8]),
            ("FOOD_PORCELAIN", [4]),
            ("PET", [1, 5, 8]),
            ("BASKETBALL", [4]),
            ("SING", [2, 7]),
            ("MILK_PINK", [2]),
            ("MILK_YELLOW", [7]),
            ("MILK_BLUEBERRY", [1, 4, 5, 8]),
        ])

    def test_uniform_preferences_override_per_baby_values(self):
        play = make_preferences()
        play[1] = "PET"
        self.assertEqual(
            resolve_preferences(play, "SING", {"SKIP", "PET", "BASKETBALL", "SING"}),
            make_preferences("SING"),
        )
        self.assertEqual(resolve_preferences(play, PER_BABY, {"SKIP", "PET", "BASKETBALL", "SING"}), play)
        self.assertEqual(set(make_preferences("FOOD_SUPER").values()), {"FOOD_SUPER"})
        self.assertIn("FOOD_BASIC", FOOD_PREFERENCES)
        self.assertIn("MILK_PINK", MILK_PREFERENCES)

    def test_live_number_templates_map_to_current_flag_identity(self):
        fixture = ROOT / "dev/fixtures/fish_baby/live_20260923/01_incubation_categories.png"
        frame = cv2.imread(str(fixture))
        templates = {
            number: cv2.imread(str(ROOT / f"assets/resource/image/fish_baby/number_{number}.png"))
            for number in range(1, 9)
        }
        located = locate_numbered_babies(frame, templates)
        self.assertEqual({number: item["baby"] for number, item in located.items()}, {
            1: (678, 405), 2: (405, 445), 3: (965, 488), 4: (612, 219),
            5: (410, 190), 6: (837, 239), 7: (230, 284), 8: (1072, 243),
        })

    def test_live_heart_and_green_check_states(self):
        base = ROOT / "dev/fixtures/fish_baby/live_20260923"
        center = (678, 405)
        self.assertEqual(count_completed_hearts(cv2.imread(str(base / "01_incubation_categories.png")), center), 0)
        self.assertEqual(count_completed_hearts(cv2.imread(str(base / "10_after_food.png")), center), 2)
        self.assertEqual(count_completed_hearts(cv2.imread(str(base / "11_after_play.png")), center), 4)
        self.assertFalse(has_green_check(cv2.imread(str(base / "03_food_selected.png")), center))
        self.assertTrue(has_green_check(cv2.imread(str(base / "04_food_one_baby_selected.png")), center))

    def test_pipeline_runs_round_and_returns_to_tank(self):
        nodes = json.loads((ROOT / "assets/resource/pipeline/features/fish_baby.json").read_text(encoding="utf-8"))
        self.assertEqual(nodes["FishBabyRunRound"]["custom_action"], "FishBabyRunRoundAction")
        self.assertEqual(nodes["FishBabyRunRound"]["next"], ["FishBabyExitIncubation"])
        self.assertEqual(nodes["FishBabyExitIncubation"]["next"], ["FishBabyExitHome"])
        self.assertEqual(nodes["FishBabyExitHome"]["next"], ["FishBabyVerifyTankAfterRound"])
        self.assertNotIn("一键孵化", json.dumps(nodes, ensure_ascii=False))

    def test_entry_retries_only_confirmed_tank_and_unknown_stops(self):
        nodes = json.loads((ROOT / "assets/resource/pipeline/features/fish_baby.json").read_text(encoding="utf-8"))
        self.assertEqual(nodes["FishBabyEntryRouter"]["next"], [
            "FishBabyAtHome", "FishBabyMainTankSky", "FishBabyAbort"])
        self.assertEqual(nodes["FishBabyMainTankSky"]["next"], ["FishBabyRetryTank"])
        self.assertEqual(nodes["FishBabyRetryTank"]["next"], ["FishBabyEntryCoral"])
        self.assertEqual(nodes["FishBabyAbort"]["action"], "StopTask")

    def test_interface_has_three_independent_preference_groups(self):
        interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
        task = next(task for task in interface["task"] if task["name"] == "鱼宝乐园")
        self.assertFalse(task["default_check"])
        self.assertEqual(task["option"], ["鱼宝喂食设置", "鱼宝玩耍设置", "鱼宝喂奶设置"])
        self.assertEqual(interface["option"]["鱼宝喂食设置"]["default_case"], "全部超级鱼食")
        self.assertEqual(interface["option"]["鱼宝玩耍设置"]["default_case"], "逐只设置")
        self.assertEqual(interface["option"]["鱼宝喂奶设置"]["default_case"], "全部蓝莓味牛奶")
        for number in range(1, 9):
            self.assertEqual(interface["option"][f"{number}号宝宝鱼食"]["default_case"], "超级鱼食")
            self.assertEqual(interface["option"][f"{number}号宝宝玩耍方式"]["default_case"], "跳过")
            self.assertEqual(interface["option"][f"{number}号宝宝牛奶"]["default_case"], "蓝莓味牛奶")


if __name__ == "__main__":
    unittest.main()
