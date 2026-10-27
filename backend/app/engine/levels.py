"""Сборщик уровней (SPEC §5.6): Location → Level.

Вид сбоку, без прыжков. Этажи — горизонтальные полосы одинаковой ширины,
соседние этажи связаны лестницей у чередующихся краёв (зигзаг), поэтому
все этажи связаны по построению. Зоны делят этаж на равные участки по
порядку объявления; объекты зоны встают в её участок с шагом не меньше
MIN_GAP тайлов и не на клетки лестниц.

Координаты — в тайлах. Персонаж стоит на клетке (floor, x).
Результат детерминирован: одни и те же данные дают один и тот же уровень.

Символы tiles: '.' пусто, '#' земля, '=' перекрытие, 'H' лестница, '|' стена.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from . import schema as s
from .issues import Issue, format_path

FLOOR_HEIGHT = 6  # тайлов между этажами: персонаж 2 тайла + запас под потолок
WIDTH = {"small": 24, "medium": 36, "large": 48}
EDGE_MARGIN = 2   # первые и последние клетки этажа — под выходы за край
MIN_GAP = 2       # минимальное расстояние между объектами одного этажа
START_X = 3


@dataclass
class BuildResult:
    level: s.Level  # строится всегда; если объект не поместился, его просто нет в level.objects
    issues: list[Issue]


def _ladder_x(width: int, lower_floor: int) -> int:
    return width - 4 if lower_floor % 2 == 0 else 3


def build_level(location: s.Location, path: str = "") -> BuildResult:
    issues: list[Issue] = []
    width = WIDTH[location.size]
    height = location.floors * FLOOR_HEIGHT + 2
    floor_y = [height - 3 - i * FLOOR_HEIGHT for i in range(location.floors)]
    x0, x1 = 1, width - 2

    tiles = [["." for _ in range(width)] for _ in range(height)]
    for x in range(width):
        tiles[height - 2][x] = tiles[height - 1][x] = "#"
    for i in range(1, location.floors):
        for x in range(x0, x1 + 1):
            tiles[floor_y[i] + 1][x] = "="

    links: list[s.LevelLink] = []
    reserved: dict[int, set[int]] = {i: set() for i in range(location.floors)}
    for i in range(location.floors - 1):
        lx = _ladder_x(width, i)
        for y in range(floor_y[i + 1] + 1, floor_y[i] + 1):
            tiles[y][lx] = "H"
        links.append(s.LevelLink(kind="ladder", a=(i, lx), b=(i + 1, lx)))
        reserved[i].add(lx)
        reserved[i + 1].add(lx)

    # Стены по краям, кроме этажей, где есть выход за край с этой стороны.
    open_left = {_zone_floor(location, o.zone) for o in location.objects if isinstance(o, s.Exit) and o.kind == "left_edge"}
    open_right = {_zone_floor(location, o.zone) for o in location.objects if isinstance(o, s.Exit) and o.kind == "right_edge"}
    for i in range(location.floors):
        for y in range(floor_y[i] - FLOOR_HEIGHT + 1, floor_y[i] + 1):
            if i not in open_left:
                tiles[y][0] = "|"
            if i not in open_right:
                tiles[y][width - 1] = "|"

    zones = {z.id: z for z in location.zones}
    placed: list[s.LevelObject] = []
    by_zone: dict[str, list[tuple[int, s.MapObject]]] = {}
    for idx, obj in enumerate(location.objects):
        zone = zones.get(obj.zone)
        if zone is None or zone.floor >= location.floors:
            continue  # ссылку на зону проверяет валидатор
        if isinstance(obj, s.Exit) and obj.kind != "door":
            x = x0 if obj.kind == "left_edge" else x1
            placed.append(s.LevelObject(id=obj.id, floor=zone.floor, x=x))
            reserved[zone.floor].add(x)
            continue
        by_zone.setdefault(obj.zone, []).append((idx, obj))

    for floor in range(location.floors):
        floor_zones = [z for z in location.zones if z.floor == floor]
        if not floor_zones:
            continue
        span_start, span_end = x0 + EDGE_MARGIN, x1 - EDGE_MARGIN
        seg = (span_end - span_start + 1) / len(floor_zones)
        taken = set(reserved[floor])
        for k, zone in enumerate(floor_zones):
            items = by_zone.get(zone.id, [])
            if not items:
                continue
            lo = span_start + round(k * seg)
            hi = span_start + round((k + 1) * seg) - 1
            slots = _slots(lo, hi, len(items), taken)
            if slots is None:
                zi = location.zones.index(zone)
                issues.append(Issue(
                    path=format_path(path, "zones", zi),
                    message=f"в зоне '{zone.id}' не помещаются {len(items)} объект(ов): участок {hi - lo + 1} тайлов "
                            f"(размер локации {location.size}); перенеси часть объектов в другую зону или увеличь size",
                ))
                continue
            for (idx, obj), x in zip(items, slots):
                placed.append(s.LevelObject(id=obj.id, floor=floor, x=x))
                taken.update(range(x - MIN_GAP + 1, x + MIN_GAP))

    positions = {p.id: p for p in placed}
    spawns = [s.LevelSpawn(**{"from": "default"}, floor=0, x=START_X)]
    for obj in location.objects:
        if isinstance(obj, s.Exit) and obj.id in positions:
            p = positions[obj.id]
            x = p.x + (1 if obj.kind == "left_edge" else -1 if obj.kind == "right_edge" else 0)
            if obj.to not in {sp.from_ for sp in spawns}:
                spawns.append(s.LevelSpawn(**{"from": obj.to}, floor=p.floor, x=x))

    level = s.Level(
        width=width, height=height,
        tiles=["".join(row) for row in tiles],
        floors=[s.LevelFloor(y=floor_y[i], x0=x0, x1=x1) for i in range(location.floors)],
        links=links, objects=placed, spawns=spawns,
    )
    issues += check_reachability(level, path)
    return BuildResult(level, issues)


def _zone_floor(location: s.Location, zone_id: str) -> int | None:
    return next((z.floor for z in location.zones if z.id == zone_id), None)


def _slots(lo: int, hi: int, n: int, taken: set[int]) -> list[int] | None:
    """n позиций в [lo, hi], равномерно, не ближе MIN_GAP друг к другу и не на занятых клетках."""
    free = [x for x in range(lo, hi + 1) if x not in taken]
    if not free:
        return None
    # жадно: целевые точки равномерно по участку, берём ближайшую свободную, соблюдая зазор
    targets = [lo + (hi - lo) * (i + 1) / (n + 1) for i in range(n)]
    chosen: list[int] = []
    for t in targets:
        options = [x for x in free if all(abs(x - c) >= MIN_GAP for c in chosen) and (not chosen or x > chosen[-1])]
        if not options:
            return None
        chosen.append(min(options, key=lambda x: (abs(x - t), x)))
    return chosen


# --- навигация ---------------------------------------------------------------------

Cell = tuple[int, int]  # (floor, x)


def neighbors(level: s.Level, cell: Cell) -> list[Cell]:
    floor, x = cell
    f = level.floors[floor]
    out = [(floor, nx) for nx in (x - 1, x + 1) if f.x0 <= nx <= f.x1]
    for link in level.links:
        a, b = tuple(link.a), tuple(link.b)
        if cell == a:
            out.append(b)
        elif cell == b:
            out.append(a)
    return out


def find_path(level: s.Level, start: Cell, goal: Cell) -> list[Cell] | None:
    """Кратчайший путь по этажам и лестницам (BFS). Та же логика — во frontend/src/engine/pathfinding.ts."""
    prev: dict[Cell, Cell | None] = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = [cell]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return path[::-1]
        for nxt in neighbors(level, cell):
            if nxt not in prev:
                prev[nxt] = cell
                queue.append(nxt)
    return None


def reachable(level: s.Level, start: Cell) -> set[Cell]:
    seen = {start}
    queue = deque([start])
    while queue:
        for nxt in neighbors(level, queue.popleft()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def check_reachability(level: s.Level, path: str = "") -> list[Issue]:
    issues = []
    for spawn in level.spawns:
        seen = reachable(level, (spawn.floor, spawn.x))
        for obj in level.objects:
            if (obj.floor, obj.x) not in seen:
                issues.append(Issue(path=path, message=f"объект '{obj.id}' недостижим от точки появления '{spawn.from_}'"))
    return issues


def spawn_for(level: s.Level, came_from: str | None) -> s.LevelSpawn:
    by_from = {sp.from_: sp for sp in level.spawns}
    return by_from.get(came_from or "", by_from["default"])


def build_all(game: s.Game) -> list[Issue]:
    """Строит уровни всех локаций и кладёт в game.levels. Возвращает проблемы сборки."""
    issues: list[Issue] = []
    game.levels = {}
    for i, loc in enumerate(game.locations):
        result = build_level(loc, format_path("locations", i))
        issues += result.issues
        game.levels[loc.id] = result.level
    return issues
