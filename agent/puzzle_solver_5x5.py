"""5x5/6x6 每日魔幻拼图的有界启发式求解器。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from heapq import heappop, heappush
from itertools import count
import time
from typing import Iterable

try:
    from .puzzle_solver import (
        PUZZLE_SPEC_5X5,
        PUZZLE_SPEC_6X6,
        PuzzleMove,
        PuzzleSpec,
        apply_move_for_spec,
        goal_states_for_spec,
        is_goal_for_spec,
        moves_for_spec,
        validate_state_for_spec,
    )
except ImportError:  # Agent 发布环境把 agent/ 直接加入 sys.path。
    from puzzle_solver import (
        PUZZLE_SPEC_5X5,
        PUZZLE_SPEC_6X6,
        PuzzleMove,
        PuzzleSpec,
        apply_move_for_spec,
        goal_states_for_spec,
        is_goal_for_spec,
        moves_for_spec,
        validate_state_for_spec,
    )


@dataclass(frozen=True, slots=True)
class PuzzleSearchStats:
    expanded_states: int
    elapsed_seconds: float
    solution_moves: int


class PuzzleSearchBudgetExceeded(RuntimeError):
    def __init__(self, stats: PuzzleSearchStats, grid_size: int = 5) -> None:
        super().__init__(f"{grid_size}×{grid_size} 求解超过安全搜索预算")
        self.stats = stats


@lru_cache(maxsize=1)
def _six_by_six_pair_distance_tables() -> tuple[dict[tuple[int, int], int], ...]:
    """两个相邻目标块的精确小型 PDB；每张表仅 36P2=1260 个状态。"""

    spec = PUZZLE_SPEC_6X6
    size = spec.grid_size
    moves = moves_for_spec(spec)

    def apply_pair(state: tuple[int, int], move: PuzzleMove) -> tuple[int, int]:
        moved: list[int] = []
        for position in state:
            row, col = divmod(position, size)
            if move.axis == "row" and row == move.index:
                col = (col + move.shift) % size
            elif move.axis == "col" and col == move.index:
                row = (row + move.shift) % size
            moved.append(row * size + col)
        return moved[0], moved[1]

    tables: list[dict[tuple[int, int], int]] = []
    for vertical in (False, True):
        goals = (
            tuple(
                (row * size + col, (row + 1) * size + col)
                for row in range(size - 1)
                for col in range(size)
            )
            if vertical
            else tuple(
                (row * size + col, row * size + col + 1)
                for row in range(size)
                for col in range(size - 1)
            )
        )
        distance = {goal: 0 for goal in goals}
        queue = deque(goals)
        while queue:
            state = queue.popleft()
            next_distance = distance[state] + 1
            for move in moves:
                predecessor = apply_pair(state, move)
                if predecessor in distance:
                    continue
                distance[predecessor] = next_distance
                queue.append(predecessor)
        tables.append(distance)
    return tuple(tables)


class PuzzleHeuristicSolver:
    """带状态去重、同线动作剪枝和双重预算的 weighted A*。"""

    def __init__(
        self,
        spec: PuzzleSpec,
        max_expanded_states: int = 300_000,
        max_seconds: float = 8.0,
        heuristic_weight: float = 1.8,
    ) -> None:
        self.spec = spec
        self.moves = moves_for_spec(self.spec)
        self.goals = goal_states_for_spec(self.spec)
        self.max_expanded_states = max_expanded_states
        self.max_seconds = max_seconds
        self.heuristic_weight = heuristic_weight
        self.last_stats = PuzzleSearchStats(0, 0.0, 0)
        self._heuristic_cache: dict[tuple[int, ...], int] = {}
        cell_count = self.spec.grid_size * self.spec.grid_size
        self._distance = tuple(
            tuple(self._toroidal_distance(source, target) for target in range(cell_count))
            for source in range(cell_count)
        )
        self._adjacent_pairs = tuple(
            (piece, piece + 1)
            for piece in range(self.spec.piece_count)
            if piece % self.spec.target_size != self.spec.target_size - 1
        ) + tuple(
            (piece, piece + self.spec.target_size)
            for piece in range(self.spec.piece_count - self.spec.target_size)
        )

    def _toroidal_distance(self, source: int, target: int) -> int:
        size = self.spec.grid_size
        source_row, source_col = divmod(source, size)
        target_row, target_col = divmod(target, size)
        row_delta = abs(source_row - target_row)
        col_delta = abs(source_col - target_col)
        return min(row_delta, size - row_delta) + min(col_delta, size - col_delta)

    def _heuristic(self, state: tuple[int, ...]) -> int:
        cached = self._heuristic_cache.get(state)
        if cached is not None:
            return cached

        distance = min(
            sum(self._distance[position][target] for position, target in zip(state, goal))
            for goal in self.goals
        )
        size = self.spec.grid_size
        target_size = self.spec.target_size
        if size == 6:
            horizontal_distance, vertical_distance = _six_by_six_pair_distance_tables()
            pair_distance = sum(
                (horizontal_distance if second == first + 1 else vertical_distance)[
                    (state[first], state[second])
                ]
                for first, second in self._adjacent_pairs
            )
            value = distance + 3 * pair_distance
        else:
            correct_adjacencies = 0
            for first, second in self._adjacent_pairs:
                first_row, first_col = divmod(state[first], size)
                second_row, second_col = divmod(state[second], size)
                if second == first + 1:
                    correct_adjacencies += (
                        first_row == second_row and second_col == first_col + 1
                    )
                else:
                    correct_adjacencies += (
                        first_col == second_col and second_row == first_row + 1
                    )
            edge_count = 2 * target_size * (target_size - 1)
            value = distance + 2 * (edge_count - correct_adjacencies)
        self._heuristic_cache[state] = value
        return value

    @staticmethod
    def _same_line(first: PuzzleMove | None, second: PuzzleMove) -> bool:
        return first is not None and first.axis == second.axis and first.index == second.index

    def solve(self, positions: Iterable[int]) -> tuple[PuzzleMove, ...]:
        start = validate_state_for_spec(positions, self.spec)
        started_at = time.monotonic()
        if is_goal_for_spec(start, self.spec):
            self.last_stats = PuzzleSearchStats(0, time.monotonic() - started_at, 0)
            return ()

        serial = count()
        best_cost = {start: 0}
        parent: dict[tuple[int, ...], tuple[tuple[int, ...], PuzzleMove]] = {}
        last_move: dict[tuple[int, ...], PuzzleMove | None] = {start: None}
        queue: list[tuple[float, int, int, int, tuple[int, ...]]] = []
        start_h = self._heuristic(start)
        heappush(queue, (self.heuristic_weight * start_h, start_h, next(serial), 0, start))
        expanded = 0

        while queue:
            if expanded >= self.max_expanded_states or time.monotonic() - started_at >= self.max_seconds:
                stats = PuzzleSearchStats(expanded, time.monotonic() - started_at, 0)
                self.last_stats = stats
                raise PuzzleSearchBudgetExceeded(stats, self.spec.grid_size)

            _, _, _, cost, state = heappop(queue)
            if cost != best_cost.get(state):
                continue
            previous_move = last_move[state]
            expanded += 1

            for move in self.moves:
                if self._same_line(previous_move, move):
                    continue
                next_state = apply_move_for_spec(state, move, self.spec)
                next_cost = cost + 1
                if next_cost >= best_cost.get(next_state, 1 << 30):
                    continue
                best_cost[next_state] = next_cost
                parent[next_state] = (state, move)
                last_move[next_state] = move
                if is_goal_for_spec(next_state, self.spec):
                    solution: list[PuzzleMove] = []
                    current = next_state
                    while current != start:
                        current, step = parent[current]
                        solution.append(step)
                    solution.reverse()
                    self.last_stats = PuzzleSearchStats(
                        expanded, time.monotonic() - started_at, len(solution)
                    )
                    return tuple(solution)
                heuristic = self._heuristic(next_state)
                priority = next_cost + self.heuristic_weight * heuristic
                heappush(
                    queue,
                    (priority, heuristic, next(serial), next_cost, next_state),
                )

        stats = PuzzleSearchStats(expanded, time.monotonic() - started_at, 0)
        self.last_stats = stats
        raise PuzzleSearchBudgetExceeded(stats, self.spec.grid_size)


class Puzzle5x5Solver(PuzzleHeuristicSolver):
    def __init__(
        self,
        max_expanded_states: int = 300_000,
        max_seconds: float = 8.0,
        heuristic_weight: float = 1.8,
    ) -> None:
        super().__init__(
            PUZZLE_SPEC_5X5,
            max_expanded_states=max_expanded_states,
            max_seconds=max_seconds,
            heuristic_weight=heuristic_weight,
        )


class Puzzle6x6Solver(PuzzleHeuristicSolver):
    def __init__(
        self,
        max_expanded_states: int = 400_000,
        max_seconds: float = 12.0,
        heuristic_weight: float = 2.4,
    ) -> None:
        super().__init__(
            PUZZLE_SPEC_6X6,
            max_expanded_states=max_expanded_states,
            max_seconds=max_seconds,
            heuristic_weight=heuristic_weight,
        )
