"""每日魔幻拼图的 MAA Swipe 坐标适配层。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

try:
    from .puzzle_solver import PuzzleMove
except ImportError:  # Agent 发布环境把 agent/ 直接加入 sys.path。
    from puzzle_solver import PuzzleMove


BOARD_ROI = (366, 85, 552, 548)
GRID_X = (435, 573, 712, 850)
GRID_Y = (152, 290, 428, 566)
DEFAULT_SWIPE_DURATION_MS = 400


@dataclass(frozen=True, slots=True)
class PuzzleGeometry:
    grid_size: int
    top_left_cell_roi: tuple[int, int, int, int]
    bottom_right_cell_roi: tuple[int, int, int, int]
    round_odd_centers_up: bool = True

    def _center(self, roi: tuple[int, int, int, int]) -> tuple[int, int]:
        x, y, width, height = roi
        rounding = 1 if self.round_odd_centers_up else 0
        return (2 * x + width + rounding) // 2, (2 * y + height + rounding) // 2

    @staticmethod
    def _interpolate(start: int, end: int, count: int) -> tuple[int, ...]:
        return tuple(round(start + index * (end - start) / (count - 1)) for index in range(count))

    @property
    def grid_x(self) -> tuple[int, ...]:
        start_x, _ = self._center(self.top_left_cell_roi)
        end_x, _ = self._center(self.bottom_right_cell_roi)
        return self._interpolate(start_x, end_x, self.grid_size)

    @property
    def grid_y(self) -> tuple[int, ...]:
        _, start_y = self._center(self.top_left_cell_roi)
        _, end_y = self._center(self.bottom_right_cell_roi)
        return self._interpolate(start_y, end_y, self.grid_size)

    @property
    def board_roi(self) -> tuple[int, int, int, int]:
        left, top, _, _ = self.top_left_cell_roi
        right_x, bottom_y, right_width, bottom_height = self.bottom_right_cell_roi
        return left, top, right_x + right_width - left, bottom_y + bottom_height - top


PUZZLE_GEOMETRY_4X4 = PuzzleGeometry(4, (366, 85, 137, 134), (781, 499, 137, 134))
PUZZLE_GEOMETRY_5X5 = PuzzleGeometry(5, (367, 86, 109, 110), (806, 525, 109, 109))
PUZZLE_GEOMETRY_6X6 = PuzzleGeometry(
    6, (365, 82, 91, 91), (825, 545, 91, 91), round_odd_centers_up=False
)

SwipeCommand = tuple[int, int, int, int, int]


class _SwipeJob(Protocol):
    def wait(self):
        ...


class _MaaController(Protocol):
    def post_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> _SwipeJob:
        ...


def puzzle_move_to_swipe(
    move: PuzzleMove,
    duration_ms: int = DEFAULT_SWIPE_DURATION_MS,
    geometry: PuzzleGeometry = PUZZLE_GEOMETRY_4X4,
) -> SwipeCommand:
    """将结构化拼图动作转换为 MAA screencap 坐标系中的 Swipe。"""

    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")

    if move.index >= geometry.grid_size or abs(move.shift) > geometry.grid_size // 2:
        raise ValueError(f"move {move} is invalid for {geometry.grid_size}x{geometry.grid_size}")
    distance = abs(move.shift)
    start_index, end_index = (0, distance) if move.shift > 0 else (distance, 0)
    grid_x, grid_y = geometry.grid_x, geometry.grid_y

    if move.axis == "row":
        y = grid_y[move.index]
        return grid_x[start_index], y, grid_x[end_index], y, duration_ms

    x = grid_x[move.index]
    return x, grid_y[start_index], x, grid_y[end_index], duration_ms


class MaaPuzzleExecutor:
    """把每个 PuzzleMove 作为一次 MAA Swipe 同步提交。"""

    def __init__(
        self,
        controller: _MaaController,
        duration_ms: int = DEFAULT_SWIPE_DURATION_MS,
        geometry: PuzzleGeometry = PUZZLE_GEOMETRY_4X4,
    ) -> None:
        self._controller = controller
        self._duration_ms = duration_ms
        self._geometry = geometry

    def execute(self, move: PuzzleMove) -> None:
        job = self._controller.post_swipe(
            *puzzle_move_to_swipe(move, self._duration_ms, self._geometry)
        )
        if job is None:
            raise RuntimeError("MAA controller did not create a swipe job")
        job.wait()
