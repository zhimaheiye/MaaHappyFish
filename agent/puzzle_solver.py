"""每日魔幻拼图的结构化动作与 4x4 最少 Swipe 求解器。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Literal, Protocol


BOARD_SIZE = 4
PIECE_COUNT = 4
VALID_SHIFTS = (-1, 1, 2)

PuzzleAxis = Literal["row", "col"]
PuzzleState = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class PuzzleSpec:
    grid_size: int
    target_size: int
    piece_count: int

    def __post_init__(self) -> None:
        if self.grid_size < 2 or not 1 <= self.target_size <= self.grid_size:
            raise ValueError("invalid puzzle dimensions")
        if self.piece_count != self.target_size * self.target_size:
            raise ValueError("piece_count must equal target_size squared")


PUZZLE_SPEC_4X4 = PuzzleSpec(4, 2, 4)
PUZZLE_SPEC_5X5 = PuzzleSpec(5, 3, 9)
PUZZLE_SPEC_6X6 = PuzzleSpec(6, 4, 16)


@dataclass(frozen=True, slots=True)
class PuzzleMove:
    """一次完整行或列的循环移动。正数表示右/下，负数表示左/上。"""

    axis: PuzzleAxis
    index: int
    shift: int

    def __post_init__(self) -> None:
        if self.axis not in ("row", "col"):
            raise ValueError(f"unsupported axis: {self.axis!r}")
        if not 0 <= self.index < 6:
            raise ValueError(f"index must be 0..5, got {self.index}")
        if self.shift not in (-2, -1, 1, 2, 3):
            raise ValueError(f"unsupported shift: {self.shift}")

    def inverse(self, grid_size: int = BOARD_SIZE) -> "PuzzleMove":
        inverse_shift = -self.shift
        if grid_size % 2 == 0 and abs(self.shift) == grid_size // 2:
            inverse_shift = grid_size // 2
        return PuzzleMove(self.axis, self.index, inverse_shift)

    def to_chinese(self) -> str:
        direction = {
            ("row", -2): "左移2格",
            ("row", -1): "左移1格",
            ("row", 1): "右移1格",
            ("row", 2): "右移2格",
            ("row", 3): "右移3格",
            ("col", -2): "上移2格",
            ("col", -1): "上移1格",
            ("col", 1): "下移1格",
            ("col", 2): "下移2格",
            ("col", 3): "下移3格",
        }[(self.axis, self.shift)]
        line = "行" if self.axis == "row" else "列"
        return f"第{self.index + 1}{line}{direction}"


ALL_MOVES: tuple[PuzzleMove, ...] = tuple(
    PuzzleMove(axis, index, shift)
    for axis in ("row", "col")
    for index in range(BOARD_SIZE)
    for shift in VALID_SHIFTS
)

GOAL_STATES: tuple[PuzzleState, ...] = tuple(
    (
        row * BOARD_SIZE + col,
        row * BOARD_SIZE + col + 1,
        (row + 1) * BOARD_SIZE + col,
        (row + 1) * BOARD_SIZE + col + 1,
    )
    for row in range(BOARD_SIZE - 1)
    for col in range(BOARD_SIZE - 1)
)
_GOAL_STATE_SET = frozenset(GOAL_STATES)


def validate_state(positions: Iterable[int]) -> PuzzleState:
    state = tuple(positions)
    if len(state) != PIECE_COUNT:
        raise ValueError(f"exactly four piece positions are required, got {len(state)}")
    if any(not isinstance(position, int) or not 0 <= position < 16 for position in state):
        raise ValueError(f"piece positions must be integers from 0 to 15: {state}")
    if len(set(state)) != PIECE_COUNT:
        raise ValueError(f"piece positions must be unique: {state}")
    return state  # type: ignore[return-value]


def apply_move(state: PuzzleState, move: PuzzleMove) -> PuzzleState:
    """应用一次循环行/列移动，只跟踪编号块，空白格无需编号。"""

    moved: list[int] = []
    for position in state:
        row, col = divmod(position, BOARD_SIZE)
        if move.axis == "row" and row == move.index:
            col = (col + move.shift) % BOARD_SIZE
        elif move.axis == "col" and col == move.index:
            row = (row + move.shift) % BOARD_SIZE
        moved.append(row * BOARD_SIZE + col)
    return tuple(moved)  # type: ignore[return-value]


@lru_cache(maxsize=3)
def moves_for_spec(spec: PuzzleSpec) -> tuple[PuzzleMove, ...]:
    shifts = {
        4: VALID_SHIFTS,
        5: (-2, -1, 1, 2),
        6: (-2, -1, 1, 2, 3),
    }.get(spec.grid_size)
    if shifts is None:
        raise ValueError(f"unsupported puzzle grid size: {spec.grid_size}")
    return tuple(
        PuzzleMove(axis, index, shift)
        for axis in ("row", "col")
        for index in range(spec.grid_size)
        for shift in shifts
    )


@lru_cache(maxsize=3)
def goal_states_for_spec(spec: PuzzleSpec) -> tuple[tuple[int, ...], ...]:
    return tuple(
        tuple(
            (anchor_row + piece_row) * spec.grid_size + anchor_col + piece_col
            for piece_row in range(spec.target_size)
            for piece_col in range(spec.target_size)
        )
        for anchor_row in range(spec.grid_size - spec.target_size + 1)
        for anchor_col in range(spec.grid_size - spec.target_size + 1)
    )


def validate_state_for_spec(positions: Iterable[int], spec: PuzzleSpec) -> tuple[int, ...]:
    state = tuple(positions)
    if len(state) != spec.piece_count:
        raise ValueError(
            f"exactly {spec.piece_count} piece positions are required, got {len(state)}"
        )
    maximum = spec.grid_size * spec.grid_size
    if any(not isinstance(position, int) or not 0 <= position < maximum for position in state):
        raise ValueError(f"piece positions must be integers from 0 to {maximum - 1}: {state}")
    if len(set(state)) != spec.piece_count:
        raise ValueError(f"piece positions must be unique: {state}")
    return state


def apply_move_for_spec(
    state: tuple[int, ...], move: PuzzleMove, spec: PuzzleSpec
) -> tuple[int, ...]:
    if move.index >= spec.grid_size or move not in moves_for_spec(spec):
        raise ValueError(f"move {move} is not valid for {spec.grid_size}x{spec.grid_size}")
    moved: list[int] = []
    for position in state:
        row, col = divmod(position, spec.grid_size)
        if move.axis == "row" and row == move.index:
            col = (col + move.shift) % spec.grid_size
        elif move.axis == "col" and col == move.index:
            row = (row + move.shift) % spec.grid_size
        moved.append(row * spec.grid_size + col)
    return tuple(moved)


def apply_moves_for_spec(
    state: tuple[int, ...], moves: Iterable[PuzzleMove], spec: PuzzleSpec
) -> tuple[int, ...]:
    for move in moves:
        state = apply_move_for_spec(state, move, spec)
    return state


def is_goal_for_spec(state: tuple[int, ...], spec: PuzzleSpec) -> bool:
    return state in _goal_state_set_for_spec(spec)


@lru_cache(maxsize=3)
def _goal_state_set_for_spec(spec: PuzzleSpec) -> frozenset[tuple[int, ...]]:
    return frozenset(goal_states_for_spec(spec))


def apply_moves(state: PuzzleState, moves: Iterable[PuzzleMove]) -> PuzzleState:
    for move in moves:
        state = apply_move(state, move)
    return state


def is_goal(state: PuzzleState) -> bool:
    """只接受棋盘内部的普通连续 2x2，不允许跨边界。"""

    return state in _GOAL_STATE_SET


@lru_cache(maxsize=1)
def _build_reverse_bfs() -> tuple[dict[PuzzleState, PuzzleMove], dict[PuzzleState, int]]:
    """从 9 个终态反向遍历，生成每个状态通往最近终态的一步策略。"""

    policy: dict[PuzzleState, PuzzleMove] = {}
    distance = {goal: 0 for goal in GOAL_STATES}
    queue: deque[PuzzleState] = deque(GOAL_STATES)

    while queue:
        state = queue.popleft()
        next_distance = distance[state] + 1
        for move in ALL_MOVES:
            predecessor = apply_move(state, move)
            if predecessor in distance:
                continue
            distance[predecessor] = next_distance
            policy[predecessor] = move.inverse()
            queue.append(predecessor)

    return policy, distance


class PuzzleSolver:
    """复用一次预计算表，为任意合法状态返回最少 Swipe 序列。"""

    def __init__(self) -> None:
        self._policy, self._distance = _build_reverse_bfs()

    @property
    def state_count(self) -> int:
        return len(self._distance)

    def minimum_distance(self, positions: Iterable[int]) -> int:
        state = validate_state(positions)
        return self._distance[state]

    def solve(self, positions: Iterable[int]) -> tuple[PuzzleMove, ...]:
        state = validate_state(positions)
        moves: list[PuzzleMove] = []
        while not is_goal(state):
            move = self._policy[state]
            moves.append(move)
            state = apply_move(state, move)
        return tuple(moves)


class PuzzleExecutor(Protocol):
    """将结构化动作映射到实际 Swipe；屏幕坐标由具体实现负责。"""

    def execute(self, move: PuzzleMove) -> None:
        ...


def execute_moves(executor: PuzzleExecutor, moves: Iterable[PuzzleMove]) -> None:
    for move in moves:
        executor.execute(move)
