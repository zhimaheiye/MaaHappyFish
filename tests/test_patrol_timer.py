import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent import my_reco


class FakeContext:
    def __init__(self):
        self.pipeline = None

    def override_pipeline(self, pipeline):
        self.pipeline = pipeline


def make_argv(task_id, interval):
    return SimpleNamespace(
        custom_recognition_param=json.dumps({"interval": interval}),
        task_detail=SimpleNamespace(task_id=task_id),
    )


def make_feature_argv(task_id, feature, interval=3600):
    return SimpleNamespace(
        custom_recognition_param=json.dumps(
            {"feature": feature, "interval": interval}
        ),
        task_detail=SimpleNamespace(task_id=task_id),
    )


class PatrolTimerTest(unittest.TestCase):
    def setUp(self):
        my_reco.patrol_timer_state.update(
            task_id=None,
            last_cycle_time=0.0,
            interval_seconds=1800.0,
        )
        self.recognition = my_reco.CheckPatrolTimerReco()
        self.context = FakeContext()

    def test_first_wait_starts_after_completed_initial_cycle(self):
        with patch.object(my_reco.time, "time", side_effect=[100.0, 129.0, 130.0]):
            self.assertIsNone(self.recognition.analyze(self.context, make_argv(1, 30)))
            self.assertIsNone(self.recognition.analyze(self.context, make_argv(1, 30)))
            self.assertIsNotNone(self.recognition.analyze(self.context, make_argv(1, 30)))
        self.assertEqual(
            self.context.pipeline["PatrolTimerDue"]["focus"]["Node.Recognition.Succeeded"],
            "[巡检] 间隔已到，开始新一轮巡检。",
        )

    def test_new_task_does_not_reuse_previous_task_clock(self):
        with patch.object(my_reco.time, "time", side_effect=[100.0, 200.0]):
            self.assertIsNone(self.recognition.analyze(self.context, make_argv(1, 30)))
            self.assertIsNone(self.recognition.analyze(self.context, make_argv(2, 30)))
        self.assertEqual(my_reco.patrol_timer_state["task_id"], 2)
        self.assertEqual(my_reco.patrol_timer_state["last_cycle_time"], 200.0)

    def test_interval_is_clamped_to_positive_value(self):
        with patch.object(my_reco.time, "time", return_value=100.0):
            self.assertIsNone(self.recognition.analyze(self.context, make_argv(1, 0)))
        self.assertEqual(my_reco.patrol_timer_state["interval_seconds"], 1.0)


class PatrolFeatureTimerTest(unittest.TestCase):
    def setUp(self):
        my_reco.patrol_feature_timer_state.clear()
        self.recognition = my_reco.CheckPatrolFeatureTimerReco()
        self.context = FakeContext()

    def test_each_enabled_feature_runs_immediately_then_hourly(self):
        with patch.object(my_reco.time, "time", side_effect=[100.0, 101.0, 3699.0, 3700.0]):
            self.assertIsNotNone(
                self.recognition.analyze(
                    self.context, make_feature_argv(1, "magic_summon")
                )
            )
            self.assertIsNotNone(
                self.recognition.analyze(
                    self.context, make_feature_argv(1, "gem_fusion")
                )
            )
            self.assertIsNone(
                self.recognition.analyze(
                    self.context, make_feature_argv(1, "magic_summon")
                )
            )
            self.assertIsNotNone(
                self.recognition.analyze(
                    self.context, make_feature_argv(1, "magic_summon")
                )
            )

    def test_new_patrol_task_resets_each_feature_clock(self):
        with patch.object(my_reco.time, "time", side_effect=[100.0, 200.0]):
            self.assertIsNotNone(
                self.recognition.analyze(
                    self.context, make_feature_argv(1, "magic_summon")
                )
            )
            self.assertIsNotNone(
                self.recognition.analyze(
                    self.context, make_feature_argv(2, "magic_summon")
                )
            )
        self.assertEqual(
            my_reco.patrol_feature_timer_state["magic_summon"]["task_id"], 2
        )

    def test_missing_feature_name_is_ignored(self):
        argv = SimpleNamespace(
            custom_recognition_param=json.dumps({"interval": 1}),
            task_detail=SimpleNamespace(task_id=1),
        )
        self.assertIsNone(self.recognition.analyze(self.context, argv))


if __name__ == "__main__":
    unittest.main()
