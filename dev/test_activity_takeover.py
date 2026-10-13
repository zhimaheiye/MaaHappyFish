# -*- coding: utf-8 -*-
"""DumpActivityTakeover 写包逻辑的离线测试。不连接模拟器。"""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))

from agent.activity_takeover import find_maa_log, write_takeover_package

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\x02\xfe\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _param(session, **extra):
    payload = {
        "event": "开心活动",
        "session": "20260925-120000",
        "session_dir": str(session),
        "flow_path": str(session / "flow.json"),
        "pipeline_path": str(session / "generated" / "pipeline.json"),
        "source_state": "S0003",
        "reason": "recognition_failed",
        "pipeline_node": "Activity_evt_S0003__TakeoverError",
        "expected": "开始\\(1\\)",
        "roi": [1, 2, 3, 4],
        "result_candidates": ["S0004"],
    }
    payload.update(extra)
    return payload


class TakeoverPackageTest(unittest.TestCase):
    def test_session_with_trace_and_chinese_path(self):
        with tempfile.TemporaryDirectory(prefix="接管_") as temp:
            session = Path(temp) / "开心水族箱活动经验"
            session.mkdir()
            lines = ["line-%02d" % index for index in range(12)]
            (session / "trace.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            dest, meta = write_takeover_package(
                _param(session),
                PNG,
                log_text=None,
                log_path=session / "missing.log",
                now=datetime(2026, 9, 25, 12, 0, 0),
            )
            self.assertTrue((dest / "current.png").is_file())
            self.assertGreater((dest / "current.png").stat().st_size, 8)
            tail = (dest / "trace_tail.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(tail, lines[-10:])
            self.assertNotIn("line-00", tail)
            self.assertEqual(meta["trace_status"], "ok")
            self.assertEqual(meta["log_status"], "unavailable")
            self.assertEqual(meta["screenshot_status"], "ok")
            self.assertEqual(meta["source_state"], "S0003")
            self.assertEqual(meta["reason"], "recognition_failed")
            reread = json.loads((dest / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(reread["event"], "开心活动")
            self.assertEqual(reread["roi"], [1, 2, 3, 4])
            self.assertIn("开心水族箱活动经验", str(dest))

    def test_missing_trace_and_log_still_write_package(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp)
            dest, meta = write_takeover_package(
                _param(session, reason="knowledge_frontier", result_candidates=["S0009"]),
                PNG,
                log_path=session / "not-a-log.log",
                now=datetime(2026, 9, 25, 12, 1, 0),
            )
            self.assertEqual(meta["trace_status"], "unavailable")
            self.assertEqual(meta["log_status"], "unavailable")
            self.assertEqual((dest / "trace_tail.jsonl").read_text(encoding="utf-8"), "")
            self.assertFalse((dest / "maa_log_tail.txt").exists())
            self.assertTrue((dest / "meta.json").is_file())
            self.assertEqual(meta["result_candidates"], ["S0009"])

    def test_existing_takeover_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp)
            moment = datetime(2026, 9, 25, 8, 0, 0)
            first, _meta = write_takeover_package(_param(session), PNG, now=moment)
            second, _meta2 = write_takeover_package(_param(session), PNG, now=moment)
            self.assertNotEqual(first, second)
            self.assertTrue((first / "meta.json").is_file())
            self.assertTrue((second / "meta.json").is_file())

    def test_log_file_is_used_when_given(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp)
            log_path = session / "maa.log"
            log_path.write_text("\n".join("log-%d" % i for i in range(5)) + "\n", encoding="utf-8")
            dest, meta = write_takeover_package(
                _param(session),
                PNG,
                log_path=log_path,
                now=datetime(2026, 9, 25, 9, 0, 0),
            )
            self.assertEqual(meta["log_status"], "ok")
            self.assertIn("log-4", (dest / "maa_log_tail.txt").read_text(encoding="utf-8"))

    def test_start_router_unmatched_keeps_null_source_state(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp)
            dest, meta = write_takeover_package(
                _param(
                    session,
                    reason="start_router_unmatched",
                    source_state=None,
                    known_candidates=["S0001", "S0002"],
                    result_candidates=[],
                ),
                PNG,
                log_path=session / "not-a-log.log",
                now=datetime(2026, 9, 25, 10, 0, 0),
            )
            reread = json.loads((dest / "meta.json").read_text(encoding="utf-8"))
            self.assertIsNone(reread["source_state"])
            self.assertEqual(reread["reason"], "start_router_unmatched")
            self.assertEqual(reread["known_candidates"], ["S0001", "S0002"])
            self.assertEqual(meta["screenshot_status"], "ok")

    def test_find_maa_log_does_not_invent_a_path(self):
        self.assertIsNone(find_maa_log(environ={}, extra_candidates=[]))
        with tempfile.TemporaryDirectory() as temp:
            log_dir = Path(temp)
            log_file = log_dir / "maa.log"
            log_file.write_text("ok\n", encoding="utf-8")
            found = find_maa_log(environ={"MAA_LOG_DIR": str(log_dir)}, extra_candidates=[])
            self.assertEqual(found, log_file)


if __name__ == "__main__":
    unittest.main()
