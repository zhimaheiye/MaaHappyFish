"""每日魔幻拼图的人工位置输入解析。"""

from __future__ import annotations

import re
from collections.abc import Sequence


_ROW_COL_RE = re.compile(r"^r\s*(\d+)\s*c\s*(\d+)$", re.IGNORECASE)
_COMMA_RE = re.compile(r"^(\d+)\s*[,，]\s*(\d+)$")


class PuzzlePositionError(ValueError):
    """用户填写的拼图位置无效。"""


def parse_puzzle_position(value: object, board_size: int) -> tuple[int, int]:
    """将格号、rNcN 或“行,列”解析为 1-based ``(row, col)``。"""
    if board_size < 1:
        raise ValueError("board_size 必须大于 0")

    text = str(value).strip()
    if text.isdecimal():
        cell = int(text)
        maximum = board_size * board_size
        if not 1 <= cell <= maximum:
            raise PuzzlePositionError(
                f"格号 {cell} 超出当前 {board_size}×{board_size} 棋盘范围：应为 1~{maximum}。"
            )
        row, col = divmod(cell - 1, board_size)
        return row + 1, col + 1

    match = _ROW_COL_RE.fullmatch(text) or _COMMA_RE.fullmatch(text)
    if match:
        row, col = map(int, match.groups())
        if not (1 <= row <= board_size and 1 <= col <= board_size):
            raise PuzzlePositionError(
                f"位置超出当前 {board_size}×{board_size} 棋盘范围："
                f"行应为 1~{board_size}，列应为 1~{board_size}。"
            )
        return row, col

    raise PuzzlePositionError(
        f"无法识别位置“{text}”。请填写格号、r4c2 或 4，2。"
    )


def parse_piece_positions(
    values: Sequence[object], board_size: int, piece_count: int | None = None
) -> tuple[int, ...]:
    """解析图片块位置并返回供 Solver 使用的 0-based 行优先索引。"""
    if piece_count is not None and len(values) != piece_count:
        raise PuzzlePositionError(
            f"当前规格需要填写 {piece_count} 个图片块位置，实际收到 {len(values)} 个。"
        )
    positions: list[int] = []
    occupied_by: dict[int, int] = {}
    for piece, value in enumerate(values, 1):
        row, col = parse_puzzle_position(value, board_size)
        position = (row - 1) * board_size + col - 1
        if position in occupied_by:
            raise PuzzlePositionError(
                f"图片块 {piece} 与图片块 {occupied_by[position]} 使用了重复位置 "
                f"r{row}c{col}。"
            )
        occupied_by[position] = piece
        positions.append(position)
    return tuple(positions)


def build_puzzle_board_reference(board_size: int) -> str:
    """生成当前棋盘的等宽行列/格号参考。"""
    if board_size < 1:
        raise ValueError("board_size 必须大于 0")
    label_width = len(f"R{board_size}")
    cell_width = max(len(str(board_size * board_size)), len(f"C{board_size}"))
    header = " " * (label_width + 2) + " ".join(
        f"C{col}".rjust(cell_width) for col in range(1, board_size + 1)
    )
    rows = [
        f"R{row}".rjust(label_width)
        + "  "
        + " ".join(
            str((row - 1) * board_size + col).rjust(cell_width)
            for col in range(1, board_size + 1)
        )
        for row in range(1, board_size + 1)
    ]
    return "\n".join((header, *rows))
