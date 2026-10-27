"""Примитивы для генераторов деталей: сетка символов-слотов палитры.

Координаты непрерывные: пиксель (x, y) занимает квадрат [x, x+1) × [y, y+1),
его центр — (x+0.5, y+0.5). Поэтому фигура с центром cx=24.0 симметрична
на холсте шириной 48.
"""

from __future__ import annotations

from typing import Callable, Iterable

T = "."  # прозрачный


class Grid:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.px = [[T] * w for _ in range(h)]

    # --- доступ ---

    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.px[y][x]
        return T

    def set(self, x: int, y: int, c: str) -> "Grid":
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c
        return self

    def filled(self, x: int, y: int) -> bool:
        return self.get(x, y) != T

    def cells(self) -> Iterable[tuple[int, int]]:
        for y in range(self.h):
            for x in range(self.w):
                yield x, y

    # --- рисование ---

    def fill(self, pred: Callable[[float, float], bool], c: str, over: str | None = None) -> "Grid":
        """Закрашивает пиксели, чей центр удовлетворяет pred. over — только поверх этих символов."""
        for x, y in self.cells():
            if pred(x + 0.5, y + 0.5) and (over is None or self.px[y][x] in over):
                self.px[y][x] = c
        return self

    def rect(self, x0: int, y0: int, x1: int, y1: int, c: str, over: str | None = None) -> "Grid":
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                if over is None or self.px[y][x] in over:
                    self.px[y][x] = c
        return self

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, c: str, over: str | None = None) -> "Grid":
        return self.fill(lambda x, y: ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0, c, over)

    def hline(self, x0: int, x1: int, y: int, c: str) -> "Grid":
        return self.rect(min(x0, x1), y, max(x0, x1), y, c)

    def vline(self, x: int, y0: int, y1: int, c: str) -> "Grid":
        return self.rect(x, min(y0, y1), x, max(y0, y1), c)

    def line(self, x0: int, y0: int, x1: int, y1: int, c: str) -> "Grid":
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.set(x0, y0, c)
            if x0 == x1 and y0 == y1:
                return self
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def poly(self, pts: list[tuple[float, float]], c: str, over: str | None = None) -> "Grid":
        """Заливка многоугольника (правило чётности) по центрам пикселей."""
        def inside(x: float, y: float) -> bool:
            hit = False
            j = len(pts) - 1
            for i in range(len(pts)):
                xi, yi = pts[i]
                xj, yj = pts[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    hit = not hit
                j = i
            return hit
        return self.fill(inside, c, over)

    def draw(self, rows: list[str], x0: int, y0: int) -> "Grid":
        """Вставляет ручной рисунок; '.' в нём прозрачна."""
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch != T:
                    self.set(x0 + dx, y0 + dy, ch)
        return self

    def stamp(self, other: "Grid", dx: int = 0, dy: int = 0) -> "Grid":
        for x, y in other.cells():
            if other.px[y][x] != T:
                self.set(x + dx, y + dy, other.px[y][x])
        return self

    def clear(self, pred: Callable[[float, float], bool]) -> "Grid":
        return self.fill(pred, T)

    def replace(self, src: str, dst: str) -> "Grid":
        for x, y in self.cells():
            if self.px[y][x] in src:
                self.px[y][x] = dst
        return self

    def dither(self, src: str, dst: str, phase: int = 0) -> "Grid":
        """Шахматная замена src → dst (фактура: щетина, мех, ржавчина)."""
        for x, y in self.cells():
            if self.px[y][x] in src and (x + y + phase) % 2 == 0:
                self.px[y][x] = dst
        return self

    # --- обработка ---

    def outline(self, c: str = "o", diagonal: bool = False) -> "Grid":
        """Контур снаружи всех непрозрачных пикселей."""
        steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if diagonal:
            steps += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        add = [
            (x, y) for x, y in self.cells()
            if self.px[y][x] == T and any(
                self.get(x + sx, y + sy) not in (T, c) for sx, sy in steps
            )
        ]
        for x, y in add:
            self.px[y][x] = c
        return self

    def shade(self, chars: str, side: str = "right", width: int = 2) -> "Grid":
        """Тень: пиксели из chars в пределах width от края фигуры с указанной стороны → верхний регистр.

        Край — прозрачный пиксель или контур 'o'.
        """
        sx, sy = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}[side]
        hits = []
        for x, y in self.cells():
            if self.px[y][x] not in chars:
                continue
            for d in range(1, width + 1):
                if self.get(x + sx * d, y + sy * d) in (T, "o"):
                    hits.append((x, y))
                    break
        for x, y in hits:
            self.px[y][x] = self.px[y][x].upper()
        return self

    def mirror(self) -> "Grid":
        g = Grid(self.w, self.h)
        g.px = [list(reversed(row)) for row in self.px]
        return g

    def copy(self) -> "Grid":
        g = Grid(self.w, self.h)
        g.px = [row[:] for row in self.px]
        return g

    def bbox(self) -> tuple[int, int, int, int] | None:
        xs = [x for x, y in self.cells() if self.px[y][x] != T]
        ys = [y for x, y in self.cells() if self.px[y][x] != T]
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def sprite(self, ref: tuple[int, int]) -> dict:
        """Обрезает по содержимому. anchor — координаты точки ref холста внутри спрайта."""
        box = self.bbox()
        if box is None:
            return {"w": 0, "h": 0, "anchor": [0, 0], "pixels": []}
        x0, y0, x1, y1 = box
        return {
            "w": x1 - x0 + 1,
            "h": y1 - y0 + 1,
            "anchor": [ref[0] - x0, ref[1] - y0],
            "pixels": ["".join(self.px[y][x0:x1 + 1]) for y in range(y0, y1 + 1)],
        }


def from_rows(rows: list[str]) -> Grid:
    g = Grid(max(len(r) for r in rows), len(rows))
    g.draw(rows, 0, 0)
    return g
