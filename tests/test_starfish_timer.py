import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent import my_reco


class FakeContext:
    def override_pipeline(self, pipeline):
        self.pipeline = pipeline


def make_argv(task_id, interval):
    return SimpleNamespace(
        custom_recognition_param=json.dumps({"interval": interval}),
        task_detail=SimpleNamespace(task_id=task_id),
    )


class StarfishTimerTest(unittest.TestCase):
    def setUp(self):
        my_reco.timer_state.update(
            task_id=None,
            last_feed_time=0.0,
            interval_seconds=600.0,
        )
        self.recognition = my_reco.CheckStarfishTimerReco()
        self.context = FakeContext()

    def test_feeds_immediately_once_per_task_then_waits(self):
        with (
            patch.object(my_reco.time, "time", side_effect=[100.0, 105.0, 200.0]),
            patch("builtins.print"),
        ):
            self.assertIsNotNone(
                self.recognition.analyze(self.context, make_argv(1, 600))
            )
            self.assertIsNone(
                self.recognition.analyze(self.context, make_argv(1, 600))
            )
            self.assertIsNotNone(
                self.recognition.analyze(self.context, make_argv(2, 600))
            )

    def test_disabled_feeding_stays_disabled(self):
        with patch.object(my_reco.time, "time", return_value=100.0):
            self.assertIsNone(
                self.recognition.analyze(self.context, make_argv(1, -1))
            )


if __name__ == "__main__":
    unittest.main()
