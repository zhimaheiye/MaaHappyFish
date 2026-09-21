#!/usr/bin/env python3
"""每日魔幻拼图离线标格与最短路径预览工具。"""

from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.puzzle_solver import (  # noqa: E402
    PuzzleMove,
    PuzzleSolver,
    execute_moves,
)


class PuzzleBoardSelection:
    """按点击顺序把四个不同格子标记为 1、2、3、4。"""

    def __init__(self) -> None:
        self._positions: list[int] = []

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(self._positions)

    @property
    def complete(self) -> bool:
        return len(self._positions) == 4

    def mark(self, position: int) -> int | None:
        if not 0 <= position < 16 or position in self._positions or self.complete:
            return None
        self._positions.append(position)
        return len(self._positions)

    def clear(self) -> None:
        self._positions.clear()


class PreviewPuzzleExecutor:
    """第一阶段执行器：只把动作显示并写入 stdout，不触碰游戏画面。"""

    def __init__(self, output: tk.Text) -> None:
        self._output = output
        self._step = 0

    def execute(self, move: PuzzleMove) -> None:
        self._step += 1
        line = f"{self._step}. {move.to_chinese()}"
        self._output.insert(tk.END, line + "\n")
        print(f"[每日魔幻拼图] {line}")


class DailyMagicPuzzleApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.selection = PuzzleBoardSelection()
        self.solver: PuzzleSolver | None = None
        self.cells: list[ttk.Button] = []

        root.title("MaaHappyFish - 每日魔幻拼图")
        root.resizable(False, False)
        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.grid()

        ttk.Label(
            container,
            text="依次点击游戏中图片块 1、2、3、4 所在的格子",
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=4, pady=(0, 10))

        for position in range(16):
            button = ttk.Button(
                container,
                text="",
                width=7,
                command=lambda value=position: self._mark(value),
            )
            button.grid(row=1 + position // 4, column=position % 4, ipadx=8, ipady=14, padx=2, pady=2)
            self.cells.append(button)

        controls = ttk.Frame(container)
        controls.grid(row=5, column=0, columnspan=4, pady=(12, 8), sticky="ew")
        ttk.Button(controls, text="清空 / 重新标记", command=self._clear).pack(side=tk.LEFT)
        self.solve_button = ttk.Button(
            controls,
            text="开始自动拼图",
            command=self._solve,
            state=tk.DISABLED,
        )
        self.solve_button.pack(side=tk.RIGHT)

        self.status = ttk.Label(container, text="下一次点击将标记：1")
        self.status.grid(row=6, column=0, columnspan=4, sticky="w", pady=(0, 6))

        self.output = tk.Text(container, width=44, height=12, state=tk.DISABLED)
        self.output.grid(row=7, column=0, columnspan=4)

    def _mark(self, position: int) -> None:
        label = self.selection.mark(position)
        if label is None:
            return
        self.cells[position].configure(text=str(label), state=tk.DISABLED)
        if self.selection.complete:
            self.status.configure(text="四块已标记，可以开始求解")
            self.solve_button.configure(state=tk.NORMAL)
        else:
            self.status.configure(text=f"下一次点击将标记：{len(self.selection.positions) + 1}")

    def _clear(self) -> None:
        self.selection.clear()
        for button in self.cells:
            button.configure(text="", state=tk.NORMAL)
        self.solve_button.configure(state=tk.DISABLED)
        self.status.configure(text="下一次点击将标记：1")
        self._set_output("")

    def _solve(self) -> None:
        if not self.selection.complete:
            return
        if self.solver is None:
            self.status.configure(text="正在首次预计算 43,680 个状态...")
            self.root.update_idletasks()
            self.solver = PuzzleSolver()

        moves = self.solver.solve(self.selection.positions)
        self._set_output(f"最少 Swipe 次数：{len(moves)}\n")
        self.output.configure(state=tk.NORMAL)
        if moves:
            execute_moves(PreviewPuzzleExecutor(self.output), moves)
        else:
            self.output.insert(tk.END, "当前排布已经完成。\n")
            print("[每日魔幻拼图] 当前排布已经完成")
        self.output.configure(state=tk.DISABLED)
        self.status.configure(text="已生成最短动作序列；当前版本仅显示并写日志")

    def _set_output(self, text: str) -> None:
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        if text:
            self.output.insert(tk.END, text)
        self.output.configure(state=tk.DISABLED)


def main() -> None:
    root = tk.Tk()
    DailyMagicPuzzleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
