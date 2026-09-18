# -*- coding: utf-8 -*-
"""海獭摸宝"本机每日完整运行次数"专项测试。

语义契约：
- 游戏日以凌晨 04:00 为界（game_day = now - 4h 的日期），无需定时器；
- 计数持久化在本机 %LOCALAPPDATA%/MaaHappyFish/state.json（测试用临时目录注入）；
- 只有正常业务终点（LAST_FRIEND_EXHAUSTED / FRIEND_LIST_EXHAUSTED）才 +1；
- Safety Limit（max_harvests / consecutive_exhausted）、手动停止、异常、Abort 均不计数；
- 同一次任务幂等：Finalize 重复进入只计一次；
- 计数仅作记录，不拦截任务启动；
- 计数与 total_harvests（本次任务内摸宝动作数）完全无关。
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
SEA_OTTER_PATH = ROOT / "assets/resource/pipeline/features/sea_otter_gem.json"


class MockTaskDetail:
    def __init__(self, task_id):
        self.task_id = task_id


class MockArg:
    def __init__(self, param=None, task_id=770000001):
        self.custom_action_param = json.dumps(param or {})
        self.custom_recognition_param = self.custom_action_param
        self.task_detail = MockTaskDetail(task_id)


class MockContext:
    pass


def run_tests():
    import agent.local_state as ls
    from agent.runtime_state import sea_otter_gem_state
    from agent.my_action import (
        InitSeaOtterStateAction,
        SeaOtterMarkNormalCompletionAction,
        SeaOtterFinalizeAction,
    )
    from agent.my_reco import CheckSeaOtterLimitReco

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MAAHAPPYFISH_STATE_DIR"] = tmp
        state_file = Path(tmp) / "state.json"

        # ---- 游戏日边界：04:00 刷新 ----
        assert ls.get_current_game_day(datetime(2026, 9, 19, 3, 59, 59)) == "2026-09-18"
        assert ls.get_current_game_day(datetime(2026, 9, 19, 4, 0, 0)) == "2026-09-19"
        assert ls.get_current_game_day(datetime(2026, 9, 19, 23, 30, 0)) == "2026-09-19"
        assert ls.get_current_game_day(datetime(2026, 9, 19, 0, 0, 0)) == "2026-09-18"
        print("[PASS] 游戏日边界：03:59:59 属前一天，04:00:00 起属新一天")

        # ---- Case A：文件不存在 -> count = 0 ----
        assert not state_file.exists()
        assert ls.get_sea_otter_daily_count() == 0
        print("[PASS] Case A 状态文件不存在时读取为 0")

        # ---- 跨日读取：03:30 仍算前一游戏日（读 2），04:01 惰性清零（读 0）----
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {"version": 1, "sea_otter": {"game_day": "2026-09-18", "completed_runs": 2}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        assert ls.get_sea_otter_daily_count(datetime(2026, 9, 19, 3, 30)) == 2
        assert ls.get_sea_otter_daily_count(datetime(2026, 9, 19, 4, 1)) == 0
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["sea_otter"]["game_day"] == "2026-09-19"
        assert saved["sea_otter"]["completed_runs"] == 0
        print("[PASS] 跨日读取：04:00 前保留旧计数，04:00 后惰性清零并进入新游戏日")

        # ---- Case B：记录一次 0 -> 1 ----
        state_file.write_text("{}", encoding="utf-8")  # 重置为无 sea_otter 节点
        count, limit = ls.record_sea_otter_completed_run()
        assert (count, limit) == (1, 3)
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["sea_otter"]["completed_runs"] == 1
        assert saved["sea_otter"]["last_completed_at"]
        print("[PASS] Case B 记录一次完整运行：0 -> 1（含 last_completed_at）")

        # ---- Case C：模拟 Agent/电脑重启后再次读取（helper 无内存缓存，等价新进程）----
        assert ls.get_sea_otter_daily_count() == 1
        print("[PASS] Case C 重启后（重新读盘）计数仍为 1")

        # ---- Case D：再正常完成一次 1 -> 2 ----
        count, _ = ls.record_sea_otter_completed_run()
        assert count == 2
        assert ls.get_sea_otter_daily_count() == 2
        print("[PASS] Case D 再次记录：1 -> 2")

        # ---- Case E：JSON 损坏 -> 不 crash，安全视为空状态 ----
        state_file.write_text("{不是合法JSON", encoding="utf-8")
        assert ls.get_sea_otter_daily_count() == 0
        assert ls.record_sea_otter_completed_run()[0] == 1  # 损坏后从头计数并恢复文件
        assert json.loads(state_file.read_text(encoding="utf-8"))["sea_otter"]["completed_runs"] == 1
        print("[PASS] Case E JSON 损坏：warning 后安全恢复，不中断任务")

        # ---- Init：重置幂等标志 + 启动日志 ----
        state_file.write_text("{}", encoding="utf-8")
        ls.record_sea_otter_completed_run()
        assert InitSeaOtterStateAction().run(MockContext(), MockArg()) is True
        assert sea_otter_gem_state["normal_completion"] is False
        assert sea_otter_gem_state["daily_count_recorded"] is False
        assert sea_otter_gem_state["total_harvests"] == 0
        assert sea_otter_gem_state["completion_reason"] is None
        print("[PASS] Init 重置运行状态与幂等标志，并输出今日 X/3 启动日志")

        # ---- 分类计数（Finalize / Mark / LimitReco 全部走真实 Agent 类）----
        finalize = SeaOtterFinalizeAction()
        mark = SeaOtterMarkNormalCompletionAction()
        limit_reco = CheckSeaOtterLimitReco()

        # Normal completion：+1
        InitSeaOtterStateAction().run(MockContext(), MockArg())
        assert mark.run(MockContext(), MockArg({"reason": "LAST_FRIEND_EXHAUSTED"})) is True
        assert sea_otter_gem_state["normal_completion"] is True
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 2  # 上一次记录 1 + 本次
        print("[PASS] 正常完整结束 +1（LAST_FRIEND_EXHAUSTED）")

        # 同一次任务 Finalize 重复进入：只 +1
        assert finalize.run(MockContext(), MockArg()) is True
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 2, "重复 Finalize 不得重复计数"
        print("[PASS] 幂等保护：同一次任务重复 Finalize 仍只计 1 次")

        # Manual stop / Abort / 未标记：不 +1
        InitSeaOtterStateAction().run(MockContext(), MockArg())
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 2
        print("[PASS] 手动停止/异常/Abort（未到正常终点）：不计数")

        # Safety max_harvests：不 +1，且区分出 SAFETY 原因
        InitSeaOtterStateAction().run(MockContext(), MockArg())
        sea_otter_gem_state["total_harvests"] = 200
        sea_otter_gem_state["max_harvests"] = 200
        assert limit_reco.analyze(MockContext(), MockArg()) == (0, 0, 10, 10)
        assert sea_otter_gem_state["completion_reason"] == "SAFETY_MAX_HARVESTS"
        assert sea_otter_gem_state["normal_completion"] is False
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 2
        print("[PASS] Safety max_harvests：任务终止但不计入每日次数")

        # Safety consecutive_exhausted：不 +1
        InitSeaOtterStateAction().run(MockContext(), MockArg())
        sea_otter_gem_state["consecutive_exhausted"] = 30
        sea_otter_gem_state["max_consecutive_exhausted"] = 30
        assert limit_reco.analyze(MockContext(), MockArg()) == (0, 0, 10, 10)
        assert sea_otter_gem_state["completion_reason"] == "SAFETY_CONSECUTIVE_EXHAUSTED"
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 2
        print("[PASS] Safety consecutive_exhausted：不计入每日次数")

        # 正常结束但本轮摸宝数量为 0：仍然 +1（计数依据是完整运行）
        InitSeaOtterStateAction().run(MockContext(), MockArg())
        assert mark.run(MockContext(), MockArg({"reason": "FRIEND_LIST_EXHAUSTED"})) is True
        assert sea_otter_gem_state["total_harvests"] == 0
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 3
        print("[PASS] 正常结束但摸宝 0 次：仍 +1（计数与 total_harvests 无关）")

        # 新任务 Init 后 daily_count_recorded 复位，可再次正常计数
        InitSeaOtterStateAction().run(MockContext(), MockArg(task_id=770000002))
        assert mark.run(MockContext(), MockArg({"reason": "LAST_FRIEND_EXHAUSTED"})) is True
        assert finalize.run(MockContext(), MockArg()) is True
        assert ls.get_sea_otter_daily_count() == 4
        assert sea_otter_gem_state["daily_count_recorded"] is True
        print("[PASS] 新一次任务 Init 后幂等标志复位，可再次正常计数")

        # 计数不拦截任务：超过 3/3 后任务仍正常初始化
        assert InitSeaOtterStateAction().run(MockContext(), MockArg(task_id=770000003)) is True
        print("[PASS] 达到 3/3 记录后不阻止任务启动（仅记账）")

        # ---- Pipeline 静态契约：只有 Done 挂 Finalize，两个 NORMAL 终点挂 Mark ----
        pipeline = json.loads(SEA_OTTER_PATH.read_text(encoding="utf-8"))
        done = pipeline["SeaOtterDone"]
        assert done["action"] == "Custom"
        assert done["custom_action"] == "SeaOtterFinalizeAction"
        assert pipeline["SeaOtterLastFriendExhausted"]["custom_action"] == "SeaOtterMarkNormalCompletionAction"
        assert pipeline["SeaOtterLastFriendExhausted"]["custom_action_param"]["reason"] == "LAST_FRIEND_EXHAUSTED"
        assert pipeline["SeaOtterAddFriendPage"]["custom_action"] == "SeaOtterMarkNormalCompletionAction"
        assert pipeline["SeaOtterAddFriendPage"]["custom_action_param"]["reason"] == "FRIEND_LIST_EXHAUSTED"
        mark_users = [
            name for name, node in pipeline.items()
            if node.get("custom_action") == "SeaOtterMarkNormalCompletionAction"
        ]
        assert sorted(mark_users) == ["SeaOtterAddFriendPage", "SeaOtterLastFriendExhausted"], mark_users
        # Safety 唯一入口 LimitReached 不得挂 Mark（保证 Safety 不计数）
        assert pipeline["SeaOtterLimitReached"]["action"] == "DoNothing"
        print("[PASS] Pipeline 静态契约：Mark 只挂在两个 NORMAL 终点，Done 统一 Finalize")

        # 清理环境变量，避免影响同进程其它测试
        os.environ.pop("MAAHAPPYFISH_STATE_DIR", None)

    # ---- 状态 markdown 展示层（唯一真源 = state.json）----
    from datetime import datetime as _dt
    from agent.runtime_state import sea_otter_gem_state

    with tempfile.TemporaryDirectory() as tmp2:
        os.environ["MAAHAPPYFISH_STATE_DIR"] = tmp2
        state_file = Path(tmp2) / "state.json"

        def write_state(runs, game_day=None):
            state_file.write_text(
                json.dumps({"version": 1, "sea_otter": {
                    "game_day": game_day or ls.get_current_game_day(),
                    "completed_runs": runs}}, ensure_ascii=False),
                encoding="utf-8",
            )

        # 各计数档 → 文案
        for n in (0, 2, 3):
            write_state(n)
            md = ls.build_sea_otter_status_markdown()
            assert f"{n} / 3" in md, (n, md)
            assert "今日完整运行" in md
        print("[PASS] markdown formatter：0/2/3 档文案正确")

        # 跨游戏日：旧日记录 2 次，04:00 后读取 → 0 / 3
        write_state(2, game_day="2026-09-17")
        md = ls.build_sea_otter_status_markdown(_dt(2026, 9, 18, 4, 1))
        assert "0 / 3" in md
        print("[PASS] markdown 跨游戏日：04:00 后展示归零")

        # 真源一致性：只改 state.json → regenerate → markdown 跟随
        write_state(2)
        md_path = ls.write_sea_otter_status_markdown()
        md_text = md_path.read_text(encoding="utf-8")
        assert "2 / 3" in md_text and "今日完整运行" in md_text
        print("[PASS] write_sea_otter_status_markdown：从 state.json 生成文件（展示缓存，非第二真源）")

        # Finalize 正常完成 → markdown 同步；Safety → 不变化
        from agent.my_action import SeaOtterFinalizeAction as _Fin
        write_state(1)
        sea_otter_gem_state["daily_count_recorded"] = False
        sea_otter_gem_state["normal_completion"] = True
        assert _Fin().run(MockContext(), MockArg()) is True
        assert "2 / 3" in md_path.read_text(encoding="utf-8"), "Finalize 后 markdown 必须同步为 2/3"

        sea_otter_gem_state["daily_count_recorded"] = False
        sea_otter_gem_state["normal_completion"] = False
        sea_otter_gem_state["completion_reason"] = "SAFETY_MAX_HARVESTS"
        assert _Fin().run(MockContext(), MockArg()) is True
        assert "2 / 3" in md_path.read_text(encoding="utf-8"), "Safety 结束不得改变计数"
        sea_otter_gem_state["completion_reason"] = None
        print("[PASS] Finalize → markdown 同步：正常完成 +1 跟随，Safety 不变化")

    os.environ.pop("MAAHAPPYFISH_STATE_DIR", None)

    print("[PASS] 海獭摸宝每日计数专项测试全部通过")


if __name__ == "__main__":
    run_tests()
