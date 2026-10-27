"""Поле тактического боя (SPEC §5.9): детерминированно по теме локации и id врага.

LLM поле не описывает: холмы и препятствия расставляет код, фронт только рисует
готовое поле из игры, симулятор играет на нём же.
"""

from __future__ import annotations

import random
import zlib
from collections import deque

from . import schema as s

SIZE = 7
PARTY_SPAWNS = [(0, 3), (0, 2), (0, 4), (1, 3)]
ENEMY_SPAWNS = [(6, 3), (6, 2), (6, 4), (5, 3)]
ATTEMPTS = 20
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))  # порядок важен: так же в TS (engine/tactics.ts)

# тема локации → (предметы-препятствия, число холмов, максимальная высота)
THEMES: dict[str, tuple[list[str], int, int]] = {
    "town_street": (["barrel", "crates", "lamp_post", "well", "fence"], 1, 1),
    "forest": (["pine", "tree", "bush", "boulder"], 2, 2),
    "house_interior": (["table", "chair", "bookshelf", "chest", "barrel"], 0, 1),
    "tavern": (["table", "chair", "barrel", "crates"], 1, 1),
    "cave": (["boulder", "crates"], 2, 2),
    "castle": (["pillar", "statue", "banner", "candelabra"], 1, 1),
    "office": (["table", "chair", "bookshelf"], 0, 1),
    "ship": (["console", "crates", "barrel"], 1, 1),
}
DEFAULT_THEME = "forest"


def _seed(location_id: str, foe_id: str, attempt: int) -> int:
    return zlib.crc32(f"{location_id}/{foe_id}/{attempt}".encode())


def passable_step(heights: list[list[int]], blocked: set[tuple[int, int]], a: tuple[int, int], b: tuple[int, int]) -> bool:
    x, y = b
    if not (0 <= x < SIZE and 0 <= y < SIZE) or b in blocked:
        return False
    return abs(heights[y][x] - heights[a[1]][a[0]]) <= 1


def _connected(heights: list[list[int]], blocked: set[tuple[int, int]]) -> bool:
    start = PARTY_SPAWNS[0]
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for dx, dy in NEIGHBOURS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt not in seen and passable_step(heights, blocked, cur, nxt):
                seen.add(nxt)
                queue.append(nxt)
    free = SIZE * SIZE - len(blocked)
    return all(p in seen for p in PARTY_SPAWNS + ENEMY_SPAWNS) and len(seen) == free


def _try_build(theme: str, rng: random.Random) -> s.Arena | None:
    props, hills, max_h = THEMES.get(theme, THEMES[DEFAULT_THEME])
    heights = [[0] * SIZE for _ in range(SIZE)]
    spawns = set(PARTY_SPAWNS + ENEMY_SPAWNS)
    for _ in range(hills):
        cx, cy = rng.randint(2, 4), rng.randint(0, SIZE - 1)
        for y in range(SIZE):
            for x in range(SIZE):
                if abs(x - cx) + abs(y - cy) <= 1 and (x, y) not in spawns:
                    heights[y][x] = max(heights[y][x], 1)
        if max_h >= 2 and rng.random() < 0.5 and (cx, cy) not in spawns:
            heights[cy][cx] = 2
    blocked: set[tuple[int, int]] = set()
    placed: list[s.ArenaProp] = []
    for _ in range(rng.randint(3, 6)):
        x, y = rng.randint(1, SIZE - 2), rng.randint(0, SIZE - 1)
        if (x, y) in spawns or (x, y) in blocked:
            continue
        blocked.add((x, y))
        placed.append(s.ArenaProp(x=x, y=y, id=rng.choice(props)))
    if not _connected(heights, blocked):
        return None
    cells = ["".join("#" if (x, y) in blocked else str(heights[y][x]) for x in range(SIZE)) for y in range(SIZE)]
    return s.Arena(width=SIZE, height=SIZE, cells=cells, props=placed, party=PARTY_SPAWNS, enemies=ENEMY_SPAWNS)


def build_arena(location: s.Location, foe: s.Foe) -> s.Arena:
    for attempt in range(ATTEMPTS):
        arena = _try_build(location.theme, random.Random(_seed(location.id, foe.id, attempt)))
        if arena:
            return arena
    return s.Arena(width=SIZE, height=SIZE, cells=["0" * SIZE] * SIZE, party=PARTY_SPAWNS, enemies=ENEMY_SPAWNS)


def build_arenas(game: s.Game) -> dict[str, s.Arena]:
    return {obj.id: build_arena(loc, obj) for loc in game.locations for obj in loc.objects if isinstance(obj, s.Foe)}
