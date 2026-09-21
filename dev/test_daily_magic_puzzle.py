#!/usr/bin/env python3
"""每日魔幻拼图求解器的全状态代码级验证。"""

from itertools import permutations
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.puzzle_solver import (  # noqa: E402
    ALL_MOVES,
    GOAL_STATES,
    PUZZLE_SPEC_5X5,
    PUZZLE_SPEC_6X6,
    PuzzleMove,
    PuzzleSolver,
    apply_move,
    apply_move_for_spec,
    apply_moves,
    apply_moves_for_spec,
    goal_states_for_spec,
    is_goal,
    is_goal_for_spec,
    moves_for_spec,
)
from agent.puzzle_solver_5x5 import (  # noqa: E402
    Puzzle5x5Solver,
    Puzzle6x6Solver,
    PuzzleSearchBudgetExceeded,
    PuzzleSearchStats,
)
from agent.puzzle_executor import (  # noqa: E402
    BOARD_ROI,
    DEFAULT_SWIPE_DURATION_MS,
    GRID_X,
    GRID_Y,
    MaaPuzzleExecutor,
    PUZZLE_GEOMETRY_4X4,
    PUZZLE_GEOMETRY_5X5,
    PUZZLE_GEOMETRY_6X6,
    puzzle_move_to_swipe,
)
from agent.puzzle_position import (  # noqa: E402
    PuzzlePositionError,
    build_puzzle_board_reference,
    parse_piece_positions,
    parse_puzzle_position,
)
from agent.my_action import DailyMagicPuzzleSolveAction  # noqa: E402
import agent.my_action as action_module  # noqa: E402
from tools.daily_magic_puzzle import PuzzleBoardSelection  # noqa: E402


class _FakeSwipeJob:
    def __init__(self) -> None:
        self.waited = False

    def wait(self) -> "_FakeSwipeJob":
        self.waited = True
        return self


class _FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int, int, int]] = []
        self.last_job: _FakeSwipeJob | None = None
        self.jobs: list[_FakeSwipeJob] = []

    def post_swipe(self, *args: int) -> _FakeSwipeJob:
        self.calls.append(args)
        self.last_job = _FakeSwipeJob()
        self.jobs.append(self.last_job)
        return self.last_job


def main() -> None:
    interface = json.loads((ROOT / "assets" / "interface.json").read_text(encoding="utf-8"))
    tasks = {task["name"]: task for task in interface["task"]}
    assert tasks["每日魔幻拼图"] == {
        "name": "每日魔幻拼图",
        "entry": "DailyMagicPuzzleTask",
        "default_check": False,
        "description": tasks["每日魔幻拼图"]["description"],
        "option": ["每日魔幻拼图规格"],
    }
    preset_names = {task["name"] for task in interface["preset"][0]["task"]}
    assert "每日魔幻拼图" in preset_names

    spec_option = interface["option"]["每日魔幻拼图规格"]
    assert spec_option["type"] == "select"
    assert spec_option["default_case"] == "4×4（2×2图片）"
    cases = {case["name"]: case for case in spec_option["cases"]}
    assert cases["4×4（2×2图片）"]["option"] == ["每日魔幻拼图位置"]
    assert cases["5×5（3×3图片）"]["option"] == ["每日魔幻拼图位置5x5"]
    assert cases["6×6（4×4图片）"]["option"] == ["每日魔幻拼图位置6x6"]
    assert all("pipeline_override" not in case for case in cases.values())

    option = interface["option"]["每日魔幻拼图位置"]
    assert option["type"] == "input"
    assert [field["default"] for field in option["inputs"]] == ["1", "2", "5", "6"]
    assert all(field["pipeline_type"] == "string" for field in option["inputs"])
    assert all("r4c2" in field["description"] and "4，2" in field["description"] for field in option["inputs"])
    assert "```text" in tasks["每日魔幻拼图"]["description"]
    assert option["pipeline_override"]["DailyMagicPuzzleSolve"]["custom_action_param"] == {
        "grid_size": 4,
        "target_size": 2,
        "piece_count": 4,
        "piece1": "{图片块1位置}",
        "piece2": "{图片块2位置}",
        "piece3": "{图片块3位置}",
        "piece4": "{图片块4位置}",
    }
    option_5x5 = interface["option"]["每日魔幻拼图位置5x5"]
    assert option_5x5["type"] == "input"
    assert len(option_5x5["inputs"]) == 9
    assert [field["default"] for field in option_5x5["inputs"]] == [
        "1", "2", "3", "6", "7", "8", "11", "12", "13"
    ]
    assert all(field["pipeline_type"] == "string" for field in option_5x5["inputs"])
    option_5x5_param = option_5x5["pipeline_override"]["DailyMagicPuzzleSolve"]["custom_action_param"]
    assert len(option_5x5_param) == 12
    assert {
        key: option_5x5_param[key]
        for key in ("grid_size", "target_size", "piece_count")
    } == {"grid_size": 5, "target_size": 3, "piece_count": 9}
    assert all(f"piece{piece}" in option_5x5_param for piece in range(1, 10))
    option_6x6 = interface["option"]["每日魔幻拼图位置6x6"]
    assert option_6x6["type"] == "input"
    assert len(option_6x6["inputs"]) == 16
    assert [field["default"] for field in option_6x6["inputs"]] == [
        "1", "2", "3", "4", "7", "8", "9", "10",
        "13", "14", "15", "16", "19", "20", "21", "22",
    ]
    assert all(field["pipeline_type"] == "string" for field in option_6x6["inputs"])
    option_6x6_param = option_6x6["pipeline_override"]["DailyMagicPuzzleSolve"]["custom_action_param"]
    assert len(option_6x6_param) == 19
    assert {
        key: option_6x6_param[key]
        for key in ("grid_size", "target_size", "piece_count")
    } == {"grid_size": 6, "target_size": 4, "piece_count": 16}
    assert all(f"piece{piece}" in option_6x6_param for piece in range(1, 17))

    pipeline = json.loads(
        (ROOT / "assets" / "resource" / "pipeline" / "features" / "daily_magic_puzzle.json").read_text(
            encoding="utf-8"
        )
    )
    task_node = pipeline["DailyMagicPuzzleTask"]
    assert task_node["template"] == "拼图页面_识别.png"
    assert task_node["roi"] == [0, 482, 316, 238]
    assert task_node["next"] == ["DailyMagicPuzzleSolve"]
    assert task_node["on_error"] == ["DailyMagicPuzzlePageAbort"]
    assert pipeline["DailyMagicPuzzleSolve"]["custom_action"] == "DailyMagicPuzzleSolveAction"
    default_param = pipeline["DailyMagicPuzzleSolve"]["custom_action_param"]
    assert (default_param["grid_size"], default_param["target_size"], default_param["piece_count"]) == (4, 2, 4)
    assert pipeline["DailyMagicPuzzlePageAbort"]["action"] == "StopTask"
    assert pipeline["DailyMagicPuzzleInvalidInput"]["action"] == "StopTask"
    assert (ROOT / "assets" / "resource" / "image" / "拼图页面_识别.png").is_file()

    expected_4x4 = """    C1 C2 C3 C4
R1   1  2  3  4
R2   5  6  7  8
R3   9 10 11 12
R4  13 14 15 16"""
    expected_5x5 = """    C1 C2 C3 C4 C5
R1   1  2  3  4  5
R2   6  7  8  9 10
R3  11 12 13 14 15
R4  16 17 18 19 20
R5  21 22 23 24 25"""
    expected_6x6 = """    C1 C2 C3 C4 C5 C6
R1   1  2  3  4  5  6
R2   7  8  9 10 11 12
R3  13 14 15 16 17 18
R4  19 20 21 22 23 24
R5  25 26 27 28 29 30
R6  31 32 33 34 35 36"""
    assert build_puzzle_board_reference(4) == expected_4x4
    assert build_puzzle_board_reference(5) == expected_5x5
    assert build_puzzle_board_reference(6) == expected_6x6

    for value, expected in {
        "1": (1, 1),
        "4": (1, 4),
        "5": (2, 1),
        "16": (4, 4),
        "r4c2": (4, 2),
        "R4C2": (4, 2),
        "r4C2": (4, 2),
        "R4 C2": (4, 2),
        "4，2": (4, 2),
        "4,2": (4, 2),
        " 4 ， 2 ": (4, 2),
    }.items():
        assert parse_puzzle_position(value, 4) == expected, value

    assert {
        parse_puzzle_position(value, 5) for value in ("17", "r4c2", "R4 C2", "4，2", "4,2")
    } == {(4, 2)}
    assert parse_puzzle_position("1", 5) == parse_puzzle_position("r1c1", 5) == (1, 1)
    assert parse_puzzle_position("25", 5) == parse_puzzle_position("r5c5", 5) == (5, 5)
    assert parse_puzzle_position("1，1", 5) == (1, 1)
    assert parse_puzzle_position("5，5", 5) == (5, 5)
    assert parse_piece_positions(("17", "r1c1", "2，1", "5,5"), 5) == (16, 0, 5, 24)
    assert {
        parse_puzzle_position(value, 6) for value in ("36", "r6c6", "6，6", "6,6")
    } == {(6, 6)}

    for value in ("0", "26", "r6c1", "r1c0", "6，2", "abc", "1,2,3"):
        try:
            parse_puzzle_position(value, 5)
        except PuzzlePositionError as exc:
            message = str(exc)
            assert "5×5" in message or "无法识别位置" in message, (value, message)
        else:
            raise AssertionError(f"invalid position accepted: {value!r}")
    for value in ("0", "37", "r7c1", "r1c7", "6,7", "7，6", "abc"):
        try:
            parse_puzzle_position(value, 6)
        except PuzzlePositionError:
            pass
        else:
            raise AssertionError(f"invalid 6x6 position accepted: {value!r}")

    try:
        parse_puzzle_position("4.2", 5)
    except PuzzlePositionError as exc:
        assert str(exc) == "无法识别位置“4.2”。请填写格号、r4c2 或 4，2。"
    else:
        raise AssertionError("invalid dotted position accepted")

    try:
        parse_piece_positions(("r2c3", "7", "10", "14"), 4)
    except PuzzlePositionError as exc:
        assert str(exc) == "图片块 2 与图片块 1 使用了重复位置 r2c3。"
    else:
        raise AssertionError("duplicate normalized positions accepted")

    try:
        parse_piece_positions(("1", "2", "3", "4"), 5, 9)
    except PuzzlePositionError as exc:
        assert str(exc) == "当前规格需要填写 9 个图片块位置，实际收到 4 个。"
    else:
        raise AssertionError("missing 5x5 piece positions accepted")

    solve_action = DailyMagicPuzzleSolveAction()
    action_controller = _FakeController()
    action_context = SimpleNamespace(
        tasker=SimpleNamespace(controller=action_controller, running=True, stopping=False)
    )
    assert solve_action.run(
        action_context,
        SimpleNamespace(
            custom_action_param={
                "piece1": 1,
                "piece2": 8,
                "piece3": 10,
                "piece4": 14,
                "move_delay_ms": 0,
            }
        ),
    ) is True
    expected_moves = PuzzleSolver().solve((0, 7, 9, 13))
    assert len(action_controller.calls) == len(expected_moves)
    assert action_controller.jobs and all(job.waited for job in action_controller.jobs)
    mixed_controller = _FakeController()
    mixed_context = SimpleNamespace(
        tasker=SimpleNamespace(controller=mixed_controller, running=True, stopping=False)
    )
    assert solve_action.run(
        mixed_context,
        SimpleNamespace(
            custom_action_param={
                "piece1": "r1c1",
                "piece2": "2，4",
                "piece3": " 3 , 2 ",
                "piece4": "R4 C2",
                "move_delay_ms": 0,
            }
        ),
    ) is True
    assert len(mixed_controller.calls) == len(PuzzleSolver().solve((0, 7, 9, 13)))
    assert solve_action.run(
        action_context,
        SimpleNamespace(custom_action_param={"piece1": 1, "piece2": 1, "piece3": 5, "piece4": 6}),
    ) is False

    spec_5x5 = PUZZLE_SPEC_5X5
    goal_5x5 = goal_states_for_spec(spec_5x5)[0]
    action_state_5x5 = apply_move_for_spec(goal_5x5, PuzzleMove("row", 0, 1), spec_5x5)
    action_5x5_controller = _FakeController()
    action_5x5_context = SimpleNamespace(
        tasker=SimpleNamespace(controller=action_5x5_controller, running=True, stopping=False)
    )
    action_5x5_param = {
        "grid_size": 5,
        "target_size": 3,
        "piece_count": 9,
        "move_delay_ms": 0,
        **{f"piece{piece}": position + 1 for piece, position in enumerate(action_state_5x5, 1)},
    }
    assert solve_action.run(
        action_5x5_context, SimpleNamespace(custom_action_param=action_5x5_param)
    ) is True
    assert action_5x5_controller.calls

    spec_6x6 = PUZZLE_SPEC_6X6
    goal_6x6 = goal_states_for_spec(spec_6x6)[0]
    action_state_6x6 = apply_move_for_spec(goal_6x6, PuzzleMove("row", 0, 1), spec_6x6)
    action_6x6_controller = _FakeController()
    action_6x6_context = SimpleNamespace(
        tasker=SimpleNamespace(controller=action_6x6_controller, running=True, stopping=False)
    )
    action_6x6_param = {
        "grid_size": 6,
        "target_size": 4,
        "piece_count": 16,
        "move_delay_ms": 0,
        **{f"piece{piece}": position + 1 for piece, position in enumerate(action_state_6x6, 1)},
    }
    assert solve_action.run(
        action_6x6_context, SimpleNamespace(custom_action_param=action_6x6_param)
    ) is True
    assert action_6x6_controller.calls

    class _AlwaysBudgetExceeded:
        def __init__(self, **_kwargs) -> None:
            self.last_stats = PuzzleSearchStats(0, 0.0, 0)

        def solve(self, _positions):
            raise PuzzleSearchBudgetExceeded(PuzzleSearchStats(123, 0.25, 0))

    failed_controller = _FakeController()
    failed_context = SimpleNamespace(
        tasker=SimpleNamespace(controller=failed_controller, running=True, stopping=False)
    )
    original_solver_5x5 = action_module.Puzzle5x5Solver
    action_module.Puzzle5x5Solver = _AlwaysBudgetExceeded
    try:
        assert solve_action.run(
            failed_context, SimpleNamespace(custom_action_param=action_5x5_param)
        ) is False
    finally:
        action_module.Puzzle5x5Solver = original_solver_5x5
    assert failed_controller.calls == []

    original_solver_6x6 = action_module.Puzzle6x6Solver
    action_module.Puzzle6x6Solver = _AlwaysBudgetExceeded
    failed_6x6_controller = _FakeController()
    try:
        assert solve_action.run(
            SimpleNamespace(
                tasker=SimpleNamespace(
                    controller=failed_6x6_controller, running=True, stopping=False
                )
            ),
            SimpleNamespace(custom_action_param=action_6x6_param),
        ) is False
    finally:
        action_module.Puzzle6x6Solver = original_solver_6x6
    assert failed_6x6_controller.calls == []

    selection = PuzzleBoardSelection()
    assert [selection.mark(position) for position in (5, 6, 9, 10)] == [1, 2, 3, 4]
    assert selection.positions == (5, 6, 9, 10)
    assert selection.complete
    assert selection.mark(11) is None
    selection.clear()
    assert selection.positions == () and not selection.complete

    assert len(ALL_MOVES) == 24
    assert len(set(ALL_MOVES)) == 24
    assert all(isinstance(move, PuzzleMove) for move in ALL_MOVES)
    assert {move.shift for move in ALL_MOVES} == {-1, 1, 2}

    assert BOARD_ROI == (366, 85, 552, 548)
    assert GRID_X == (435, 573, 712, 850)
    assert GRID_Y == (152, 290, 428, 566)
    assert PUZZLE_GEOMETRY_4X4.grid_x == GRID_X
    assert PUZZLE_GEOMETRY_4X4.grid_y == GRID_Y
    assert PUZZLE_GEOMETRY_4X4.board_roi == BOARD_ROI
    assert PUZZLE_GEOMETRY_5X5.top_left_cell_roi == (367, 86, 109, 110)
    assert PUZZLE_GEOMETRY_5X5.bottom_right_cell_roi == (806, 525, 109, 109)
    assert PUZZLE_GEOMETRY_5X5.grid_x == (422, 532, 642, 751, 861)
    assert PUZZLE_GEOMETRY_5X5.grid_y == (141, 251, 360, 470, 580)
    assert PUZZLE_GEOMETRY_6X6.top_left_cell_roi == (365, 82, 91, 91)
    assert PUZZLE_GEOMETRY_6X6.bottom_right_cell_roi == (825, 545, 91, 91)
    assert PUZZLE_GEOMETRY_6X6.grid_x == (410, 502, 594, 686, 778, 870)
    assert PUZZLE_GEOMETRY_6X6.grid_y == (127, 220, 312, 405, 497, 590)
    assert puzzle_move_to_swipe(PuzzleMove("row", 0, 1)) == (435, 152, 573, 152, 400)
    assert puzzle_move_to_swipe(PuzzleMove("row", 3, -1)) == (573, 566, 435, 566, 400)
    assert puzzle_move_to_swipe(PuzzleMove("row", 2, 2)) == (435, 428, 712, 428, 400)
    assert puzzle_move_to_swipe(PuzzleMove("col", 0, 1)) == (435, 152, 435, 290, 400)
    assert puzzle_move_to_swipe(PuzzleMove("col", 3, -1)) == (850, 290, 850, 152, 400)
    assert puzzle_move_to_swipe(PuzzleMove("col", 2, 2)) == (712, 152, 712, 428, 400)

    board_x, board_y, board_w, board_h = BOARD_ROI
    for move in ALL_MOVES:
        x1, y1, x2, y2, duration = puzzle_move_to_swipe(move)
        assert board_x <= x1 <= board_x + board_w and board_x <= x2 <= board_x + board_w
        assert board_y <= y1 <= board_y + board_h and board_y <= y2 <= board_y + board_h
        assert duration == DEFAULT_SWIPE_DURATION_MS
        if move.axis == "row":
            assert y1 == y2 == GRID_Y[move.index]
        else:
            assert x1 == x2 == GRID_X[move.index]

    fake_controller = _FakeController()
    executor = MaaPuzzleExecutor(fake_controller)
    executor.execute(PuzzleMove("row", 1, 1))
    assert fake_controller.calls == [(435, 290, 573, 290, 400)]
    assert fake_controller.last_job is not None and fake_controller.last_job.waited

    moves_5x5 = moves_for_spec(spec_5x5)
    assert len(moves_5x5) == 40 and len(set(moves_5x5)) == 40
    assert {move.shift for move in moves_5x5} == {-2, -1, 1, 2}
    board_x_5, board_y_5, board_w_5, board_h_5 = PUZZLE_GEOMETRY_5X5.board_roi
    for move in moves_5x5:
        x1, y1, x2, y2, duration = puzzle_move_to_swipe(
            move, geometry=PUZZLE_GEOMETRY_5X5
        )
        assert board_x_5 <= x1 <= board_x_5 + board_w_5
        assert board_x_5 <= x2 <= board_x_5 + board_w_5
        assert board_y_5 <= y1 <= board_y_5 + board_h_5
        assert board_y_5 <= y2 <= board_y_5 + board_h_5
        assert duration == DEFAULT_SWIPE_DURATION_MS
        if move.axis == "row":
            assert y1 == y2 == PUZZLE_GEOMETRY_5X5.grid_y[move.index]
            assert (x2 > x1) == (move.shift > 0)
            assert abs(x2 - x1) >= 109 * abs(move.shift)
        else:
            assert x1 == x2 == PUZZLE_GEOMETRY_5X5.grid_x[move.index]
            assert (y2 > y1) == (move.shift > 0)
            assert abs(y2 - y1) >= 109 * abs(move.shift)
    dry_run_moves = (
        PuzzleMove("row", 0, 1),
        PuzzleMove("row", 2, -2),
        PuzzleMove("col", 1, 2),
        PuzzleMove("col", 4, -1),
    )
    dry_run_commands = tuple(
        puzzle_move_to_swipe(move, geometry=PUZZLE_GEOMETRY_5X5)
        for move in dry_run_moves
    )
    for move, (x1, y1, x2, y2, _duration) in zip(dry_run_moves, dry_run_commands):
        assert board_x_5 <= x1 <= board_x_5 + board_w_5
        assert board_x_5 <= x2 <= board_x_5 + board_w_5
        assert board_y_5 <= y1 <= board_y_5 + board_h_5
        assert board_y_5 <= y2 <= board_y_5 + board_h_5
        if move.axis == "row":
            assert (x2 > x1) == (move.shift > 0)
        else:
            assert (y2 > y1) == (move.shift > 0)
    assert apply_move_for_spec(goal_5x5, PuzzleMove("row", 0, 1), spec_5x5)[:3] == (1, 2, 3)
    assert dry_run_commands[0][2] > dry_run_commands[0][0]

    moves_6x6 = moves_for_spec(spec_6x6)
    assert len(moves_6x6) == 60 and len(set(moves_6x6)) == 60
    assert {move.shift for move in moves_6x6} == {-2, -1, 1, 2, 3}
    dry_run_moves_6x6 = (
        PuzzleMove("row", 0, 1),
        PuzzleMove("row", 2, -2),
        PuzzleMove("row", 5, 3),
        PuzzleMove("col", 1, -1),
        PuzzleMove("col", 3, 2),
        PuzzleMove("col", 5, 3),
    )
    dry_run_commands_6x6 = tuple(
        puzzle_move_to_swipe(move, geometry=PUZZLE_GEOMETRY_6X6)
        for move in dry_run_moves_6x6
    )
    board_x_6, board_y_6, board_w_6, board_h_6 = PUZZLE_GEOMETRY_6X6.board_roi
    for move, (x1, y1, x2, y2, duration) in zip(
        dry_run_moves_6x6, dry_run_commands_6x6
    ):
        assert board_x_6 <= x1 <= board_x_6 + board_w_6
        assert board_x_6 <= x2 <= board_x_6 + board_w_6
        assert board_y_6 <= y1 <= board_y_6 + board_h_6
        assert board_y_6 <= y2 <= board_y_6 + board_h_6
        assert duration == DEFAULT_SWIPE_DURATION_MS
        if move.axis == "row":
            assert (x2 > x1) == (move.shift > 0)
        else:
            assert (y2 > y1) == (move.shift > 0)
    assert dry_run_commands_6x6 == (
        (410, 127, 502, 127, 400),
        (594, 312, 410, 312, 400),
        (410, 590, 686, 590, 400),
        (502, 220, 502, 127, 400),
        (686, 127, 686, 312, 400),
        (870, 127, 870, 405, 400),
    )
    assert apply_move_for_spec(goal_6x6, PuzzleMove("row", 0, 1), spec_6x6)[:4] == (1, 2, 3, 4)

    assert len(GOAL_STATES) == 9
    assert len(set(GOAL_STATES)) == 9
    assert all(is_goal(goal) for goal in GOAL_STATES)
    assert not is_goal((3, 0, 7, 4)), "horizontal wrapping must not be a goal"
    assert not is_goal((12, 13, 0, 1)), "vertical wrapping must not be a goal"

    goals_5x5 = goal_states_for_spec(spec_5x5)
    assert len(goals_5x5) == 9 and len(set(goals_5x5)) == 9
    assert all(is_goal_for_spec(goal, spec_5x5) for goal in goals_5x5)
    assert not is_goal_for_spec((3, 4, 0, 8, 9, 5, 13, 14, 10), spec_5x5)
    assert not is_goal_for_spec((15, 16, 17, 20, 21, 22, 0, 1, 2), spec_5x5)

    goals_6x6 = goal_states_for_spec(spec_6x6)
    assert len(goals_6x6) == 9 and len(set(goals_6x6)) == 9
    assert all(is_goal_for_spec(goal, spec_6x6) for goal in goals_6x6)
    horizontal_wrap_6x6 = tuple(
        row * 6 + col for row in range(4) for col in (4, 5, 0, 1)
    )
    vertical_wrap_6x6 = tuple(
        row * 6 + col for row in (4, 5, 0, 1) for col in range(4)
    )
    assert not is_goal_for_spec(horizontal_wrap_6x6, spec_6x6)
    assert not is_goal_for_spec(vertical_wrap_6x6, spec_6x6)

    solver_5x5 = Puzzle5x5Solver()
    basic_scrambles = (
        (),
        (PuzzleMove("row", 0, 1),),
        (PuzzleMove("col", 1, -1),),
        (PuzzleMove("row", 2, 2),),
        (PuzzleMove("col", 2, -2),),
        (PuzzleMove("row", 0, 1), PuzzleMove("col", 2, -2)),
    )
    for scramble in basic_scrambles:
        state = apply_moves_for_spec(goals_5x5[4], scramble, spec_5x5)
        solution = solver_5x5.solve(state)
        assert is_goal_for_spec(apply_moves_for_spec(state, solution, spec_5x5), spec_5x5)

    reported_state = tuple(position - 1 for position in (13, 11, 21, 15, 19, 2, 22, 6, 4))
    reported_solution = solver_5x5.solve(reported_state)
    assert is_goal_for_spec(
        apply_moves_for_spec(reported_state, reported_solution, spec_5x5), spec_5x5
    )

    benchmark_cases = 0
    benchmark_passed = 0
    slowest = PuzzleSearchStats(0, 0.0, 0)
    slowest_scramble = 0
    max_expanded = 0
    longest_solution = 0
    for scramble_length in (1, 2, 3, 5, 8, 10):
        for sample in range(5):
            rng = random.Random(5100 + scramble_length * 10 + sample)
            state = goals_5x5[rng.randrange(len(goals_5x5))]
            previous_move = None
            for _ in range(scramble_length):
                choices = [
                    move
                    for move in moves_5x5
                    if previous_move is None
                    or (move.axis, move.index) != (previous_move.axis, previous_move.index)
                ]
                previous_move = rng.choice(choices)
                state = apply_move_for_spec(state, previous_move, spec_5x5)
            solution = solver_5x5.solve(state)
            benchmark_cases += 1
            if is_goal_for_spec(apply_moves_for_spec(state, solution, spec_5x5), spec_5x5):
                benchmark_passed += 1
            max_expanded = max(max_expanded, solver_5x5.last_stats.expanded_states)
            longest_solution = max(longest_solution, solver_5x5.last_stats.solution_moves)
            if solver_5x5.last_stats.elapsed_seconds > slowest.elapsed_seconds:
                slowest = solver_5x5.last_stats
                slowest_scramble = scramble_length
    assert benchmark_passed == benchmark_cases == 30

    solver_6x6 = Puzzle6x6Solver()
    assert all(solver_6x6.solve(goal) == () for goal in goals_6x6)
    representative_single_moves = tuple(
        PuzzleMove(axis, index, shift)
        for axis, index in (("row", 1), ("col", 1))
        for shift in (-2, -1, 1, 2, 3)
    )
    for move in representative_single_moves:
        state = apply_move_for_spec(goals_6x6[4], move, spec_6x6)
        solution = solver_6x6.solve(state)
        assert is_goal_for_spec(apply_moves_for_spec(state, solution, spec_6x6), spec_6x6)

    benchmark_6x6: list[tuple[int, PuzzleSearchStats]] = []
    benchmark_6x6_passed = 0
    for scramble_length in (2, 3, 5, 8, 10, 15, 20):
        for sample in range(5):
            rng = random.Random(660_000 + scramble_length * 100 + sample)
            state = goals_6x6[rng.randrange(len(goals_6x6))]
            previous_move = None
            for _ in range(scramble_length):
                choices = [
                    move
                    for move in moves_6x6
                    if previous_move is None
                    or (move.axis, move.index) != (previous_move.axis, previous_move.index)
                ]
                previous_move = rng.choice(choices)
                state = apply_move_for_spec(state, previous_move, spec_6x6)
            solution = solver_6x6.solve(state)
            assert is_goal_for_spec(
                apply_moves_for_spec(state, solution, spec_6x6), spec_6x6
            )
            benchmark_6x6_passed += 1
            benchmark_6x6.append((scramble_length, solver_6x6.last_stats))
    assert benchmark_6x6_passed == len(benchmark_6x6) == 35

    solver = PuzzleSolver()
    assert solver.state_count == 43_680

    passed = 0
    for state in permutations(range(16), 4):
        distance = solver.minimum_distance(state)
        moves = solver.solve(state)
        assert len(moves) == distance, (state, len(moves), distance)

        current = state
        remaining = distance
        for move in moves:
            current = apply_move(current, move)
            remaining -= 1
            assert solver.minimum_distance(current) == remaining, (state, move, current)

        assert current == apply_moves(state, moves)
        assert is_goal(current), (state, moves, current)
        passed += 1

    assert passed == 43_680
    print("parser cases passed (4x4, 5x5, 6x6, invalid, out-of-range, duplicate, legacy numeric)")
    print("4x4 board reference:\n" + expected_4x4)
    print("5x5 board reference:\n" + expected_5x5)
    print("6x6 board reference:\n" + expected_6x6)
    print("24 / 24 swipe mappings passed")
    print(f"{passed} / 43680 states passed")
    print("40 / 40 5x5 logical moves passed")
    print(
        f"5x5 deterministic cases: {benchmark_passed} / {benchmark_cases} passed; "
        f"max expanded={max_expanded}, longest solution={longest_solution}; "
        f"slowest scramble={slowest_scramble}, expanded={slowest.expanded_states}, "
        f"solution={slowest.solution_moves}, time={slowest.elapsed_seconds:.3f}s"
    )
    print("5x5 dry run:", dry_run_commands)
    stats_20 = [stats for length, stats in benchmark_6x6 if length == 20]
    print("60 / 60 6x6 logical moves passed")
    print(f"6x6 deterministic cases: {benchmark_6x6_passed} / {len(benchmark_6x6)} passed")
    print(
        "6x6 scramble 20: "
        f"{len(stats_20)} / {len(stats_20)} passed; "
        f"avg time={sum(s.elapsed_seconds for s in stats_20) / len(stats_20):.3f}s, "
        f"max time={max(s.elapsed_seconds for s in stats_20):.3f}s, "
        f"avg expanded={sum(s.expanded_states for s in stats_20) / len(stats_20):.1f}, "
        f"max expanded={max(s.expanded_states for s in stats_20)}, "
        f"avg solution={sum(s.solution_moves for s in stats_20) / len(stats_20):.1f}, "
        f"max solution={max(s.solution_moves for s in stats_20)}"
    )
    print("6x6 dry run:", dry_run_commands_6x6)


if __name__ == "__main__":
    main()
