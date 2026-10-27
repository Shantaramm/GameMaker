"""Тайлсеты 16×16 (SPEC §5.8.5).

Тайлы не обрезаются: спрайт тайла — ровно 16×16 (двери и высокие
декорации — 16×32), anchor — левый нижний угол клетки [0, h]. Рендер
ставит его в (x·16, (y+1)·16).

Имена тайлов: floor (верхний ряд земли), fill (земля ниже), slab
(перекрытие между этажами), wall (фон помещения; у улицы нет), edge (стена
по краю уровня), ladder, door, door_open, door_locked и декорации из списка
decor. Буквы — слоты настроенческой палитры, как у фонов.
"""

from __future__ import annotations

import random

from px import T, Grid

S = 16


def tile() -> Grid:
    return Grid(S, S)


def tall() -> Grid:
    return Grid(S, 2 * S)


def raw(g: Grid) -> dict:
    return {"w": g.w, "h": g.h, "anchor": [0, g.h], "pixels": ["".join(r) for r in g.px]}


# --- узоры ----------------------------------------------------------------------------

def planks(c: str, step: int = 4, seed: int = 0) -> Grid:
    g = tile().rect(0, 0, S - 1, S - 1, c)
    for y in range(step - 1, S, step):
        g.hline(0, S - 1, y, c.upper())
    for i, y in enumerate(range(0, S, step)):
        x = (i * 7 + seed) % S
        g.vline(x, y, y + step - 2, c.upper())
    return g


def bricks(c: str, h: int = 4, w: int = 8) -> Grid:
    g = tile().rect(0, 0, S - 1, S - 1, c)
    for i, y in enumerate(range(0, S, h)):
        g.hline(0, S - 1, y + h - 1, c.upper())
        for x in range((i % 2) * (w // 2), S, w):
            g.vline(x, y, y + h - 2, c.upper())
    return g


def speckle(g: Grid, over: str, c: str, density: float, seed: str) -> Grid:
    rng = random.Random(seed)
    for x, y in g.cells():
        if g.get(x, y) in over and rng.random() < density:
            g.set(x, y, c)
    return g


def stones(c: str, seed: str) -> Grid:
    g = tile().rect(0, 0, S - 1, S - 1, c.upper())
    rng = random.Random(seed)
    for cx, cy in [(3, 3), (11, 2), (7, 9), (14, 11), (2, 13), (10, 14)]:
        g.ellipse(cx + rng.random(), cy + rng.random(), 3.2, 2.4, c)
    return g


def surface(base: Grid, top: str, rows: int = 2) -> Grid:
    return base.rect(0, 0, S - 1, rows - 1, top)


def ladder(c: str) -> Grid:
    g = tile().vline(3, 0, S - 1, c).vline(12, 0, S - 1, c)
    for y in (2, 7, 12):
        g.hline(3, 12, y, c)
    g.vline(4, 0, S - 1, c.upper()).vline(13, 0, S - 1, c.upper())
    return g


def door(c: str, frame: str, state: str) -> Grid:
    g = tall().rect(1, 4, 14, 31, frame)
    if state == "open":
        g.rect(3, 6, 12, 31, "k")
        g.rect(3, 6, 4, 31, c)
        return g
    g.rect(3, 6, 12, 31, c)
    g.rect(5, 9, 10, 16, c.upper()).rect(5, 20, 10, 28, c.upper())
    g.set(11, 19, "m")
    if state == "locked":
        g.rect(6, 17, 9, 20, "m").rect(7, 15, 8, 16, "M").set(7, 18, "k")
    return g


# --- декорации --------------------------------------------------------------------------

def barrel() -> Grid:
    g = tile().ellipse(8, 9.5, 6, 6.5, "p")
    g.clear(lambda x, y: y < 3).hline(2, 13, 5, "m").hline(2, 13, 13, "m")
    return g.outline().shade("p", "right", 2)


def crate() -> Grid:
    g = tile().rect(2, 4, 13, 15, "p")
    g.line(2, 4, 13, 15, "P").line(13, 4, 2, 15, "P").hline(2, 13, 4, "P")
    return g.outline()


def lamp_post() -> Grid:
    g = tall().rect(7, 8, 8, 31, "o").rect(5, 30, 10, 31, "o")
    g.rect(5, 2, 10, 7, "l").hline(4, 11, 1, "o").hline(5, 10, 8, "o")
    return g


def sign() -> Grid:
    g = tile().rect(7, 8, 8, 15, "p").rect(2, 2, 13, 8, "p")
    g.hline(4, 11, 4, "P").hline(4, 9, 6, "P")
    return g.outline()


def bench() -> Grid:
    g = tile().rect(1, 9, 14, 10, "p").rect(2, 11, 3, 15, "p").rect(12, 11, 13, 15, "p").rect(1, 5, 14, 6, "p")
    return g.outline()


def window(frame: str = "p") -> Grid:
    g = tile().rect(2, 2, 13, 13, frame).rect(4, 4, 11, 11, "n").vline(8, 4, 11, frame).hline(4, 11, 8, frame)
    return g.outline()


def lit_window() -> Grid:
    return tile().rect(2, 2, 13, 13, "p").rect(4, 4, 11, 11, "l").vline(8, 4, 11, "p").hline(4, 11, 8, "p").outline()


def picture() -> Grid:
    g = tile().rect(3, 3, 12, 11, "a").rect(5, 5, 10, 9, "v").rect(5, 8, 10, 9, "g")
    return g.outline()


def shelf() -> Grid:
    g = tile().rect(1, 6, 14, 7, "p")
    for x, h, c in [(2, 4, "a"), (4, 5, "v"), (6, 3, "q"), (10, 4, "a")]:
        g.rect(x, 6 - h, x + 1, 5, c)
    return g.outline()


def plant() -> Grid:
    g = tile().rect(5, 11, 10, 15, "p")
    for dx, dy, r in [(0, 0, 3), (-3, 2, 2.4), (3, 2, 2.4)]:
        g.ellipse(8 + dx, 7 + dy, r, r, "v")
    return g.outline().shade("v", "right", 1)


def clock() -> Grid:
    g = tall().rect(4, 4, 11, 31, "p").ellipse(8, 9, 3, 3, "w").set(8, 8, "o").set(9, 9, "o")
    g.rect(6, 16, 9, 26, "P").set(7, 24, "m")
    return g.outline()


def table_mug() -> Grid:
    g = tile().rect(1, 8, 14, 9, "p").rect(2, 10, 3, 15, "p").rect(12, 10, 13, 15, "p")
    g.rect(5, 4, 7, 7, "w").set(8, 5, "w")
    return g.outline()


def hearth() -> Grid:
    g = tall().rect(0, 12, 15, 31, "q").rect(3, 18, 12, 31, "k")
    g.poly([(4, 31), (6, 23), (8, 27), (10, 21), (12, 31)], "l")
    g.rect(0, 10, 15, 12, "Q")
    return bricks_on(g, "q", 12)


def bricks_on(g: Grid, c: str, top: int) -> Grid:
    for y in range(top + 3, g.h, 4):
        for x in range(g.w):
            if g.get(x, y) == c:
                g.set(x, y, c.upper())
    return g.outline()


def banner() -> Grid:
    g = tall().hline(2, 13, 2, "m").rect(3, 3, 12, 20, "a").poly([(3, 20.5), (7.5, 25), (12.5, 20.5)], "a")
    g.ellipse(8, 11, 2.5, 2.5, "l")
    return g.outline().shade("a", "right", 1)


def tree() -> Grid:
    g = tall().rect(6, 16, 9, 31, "p")
    for dx, dy, r in [(0, 0, 6.5), (-4, 5, 4.5), (4, 5, 4.5)]:
        g.ellipse(8 + dx, 9 + dy, r, r * 0.9, "v")
    return g.outline().shade("v", "right", 2)


def bush() -> Grid:
    g = tile()
    for dx, r in [(-3, 4), (0, 5), (3, 4)]:
        g.ellipse(8 + dx, 12, r, r * 0.8, "v")
    g.clear(lambda x, y: y >= 16)
    return g.outline().shade("v", "right", 1)


def mushroom() -> Grid:
    g = tile().rect(7, 9, 8, 15, "w").ellipse(8, 8, 5, 3, "a")
    g.clear(lambda x, y: y > 9 and not (7 <= x <= 8.99))
    g.set(6, 7, "w").set(10, 7, "w")
    return g.outline()


def rock() -> Grid:
    g = tile().ellipse(8, 12, 6, 4.5, "q")
    g.clear(lambda x, y: y >= 16)
    return g.outline().shade("q", "right", 2)


def flowers() -> Grid:
    g = tile()
    for x, h, c in [(3, 5, "a"), (7, 7, "l"), (11, 4, "a")]:
        g.vline(x, 15 - h, 15, "v").set(x, 14 - h, c).set(x - 1, 15 - h, c).set(x + 1, 15 - h, c)
    return g


def stalagmite() -> Grid:
    return tall().poly([(3, 31.5), (7, 14), (9, 18), (13, 31.5)], "q").outline().shade("q", "right", 2)


def crystal() -> Grid:
    g = tile().poly([(4, 15.5), (6, 6), (8, 15.5)], "l").poly([(7, 15.5), (10, 3), (13, 15.5)], "l")
    return g.outline()


def bones() -> Grid:
    g = tile().ellipse(5, 12, 2.5, 2.2, "w").set(4, 12, "k").set(6, 12, "k")
    g.line(8, 14, 14, 12, "w").line(8, 12, 13, 15, "w")
    return g.outline()


def torch() -> Grid:
    g = tile().rect(7, 8, 8, 14, "m").rect(5, 7, 10, 8, "m")
    g.poly([(5.5, 7), (7, 1), (8, 3), (9, 0), (10.5, 7)], "l")
    return g.outline()


def armor_stand() -> Grid:
    g = tall().ellipse(8, 9, 3, 3, "m").rect(4, 12, 11, 22, "m").rect(5, 23, 6, 30, "m").rect(9, 23, 10, 30, "m").rect(3, 30, 12, 31, "p")
    return g.outline().shade("m", "right", 1)


def slit_window() -> Grid:
    return tile().rect(5, 1, 10, 14, "q").rect(7, 3, 8, 12, "n").outline()


def desk() -> Grid:
    g = tile().rect(0, 7, 15, 8, "p").rect(1, 9, 5, 15, "p").rect(13, 9, 14, 15, "p").hline(2, 4, 12, "m")
    g.rect(8, 3, 12, 6, "q").set(9, 4, "l")
    return g.outline()


def cabinet() -> Grid:
    g = tall().rect(3, 10, 12, 31, "m")
    for y in (14, 21, 28):
        g.hline(3, 12, y - 3, "M").hline(7, 8, y, "o")
    return g.outline()


def poster() -> Grid:
    return tile().rect(3, 2, 12, 13, "a").rect(5, 4, 10, 8, "w").hline(5, 10, 10, "A").outline()


def cooler() -> Grid:
    g = tall().rect(4, 16, 11, 31, "w").ellipse(8, 11, 3.5, 5, "n").rect(6, 20, 9, 21, "a")
    return g.outline()


def pipes() -> Grid:
    g = tall().rect(3, 0, 5, 31, "m").rect(10, 0, 12, 31, "m").rect(3, 8, 12, 10, "m").rect(9, 18, 13, 20, "a")
    return g.outline().shade("m", "right", 1)


def console() -> Grid:
    g = tile().rect(1, 6, 14, 15, "q").poly([(1, 6), (3, 2), (12, 2), (14, 6)], "m")
    for i, x in enumerate(range(3, 13, 2)):
        g.set(x, 4, "la"[i % 2])
    g.rect(3, 9, 6, 12, "k").set(4, 10, "l")
    return g.outline()


def porthole() -> Grid:
    g = tile().ellipse(8, 8, 6, 6, "m").ellipse(8, 8, 4, 4, "k")
    g.set(6, 6, "w").set(10, 9, "w").set(7, 10, "w")
    return g.outline()


def vent() -> Grid:
    g = tile().rect(2, 4, 13, 11, "m")
    for y in (5, 7, 9):
        g.hline(3, 12, y, "k")
    return g.outline()


DECOR = {
    "barrel": barrel, "crate": crate, "lamp_post": lamp_post, "sign": sign, "bench": bench,
    "window": window, "lit_window": lit_window, "picture": picture, "shelf": shelf, "plant": plant, "clock": clock,
    "table_mug": table_mug, "hearth": hearth, "banner": banner, "tree": tree, "bush": bush, "mushroom": mushroom,
    "rock": rock, "flowers": flowers, "stalagmite": stalagmite, "crystal": crystal, "bones": bones,
    "torch": torch, "armor_stand": armor_stand, "slit_window": slit_window, "desk": desk, "cabinet": cabinet,
    "poster": poster, "cooler": cooler, "pipes": pipes, "console": console, "porthole": porthole, "vent": vent,
}
# Декорации, которые висят на стене (рисуются выше пола), а не стоят на полу.
WALL_DECOR = {"window", "lit_window", "picture", "shelf", "banner", "torch", "slit_window", "poster", "porthole", "vent"}


# --- темы -----------------------------------------------------------------------------------

def theme(id: str, description: str, setting: str, tiles: dict[str, Grid], decor: list[str]) -> dict:
    return {
        "id": id, "slot": "tileset", "description": description, "setting": setting,
        "tiles": {name: raw(g) for name, g in tiles.items()},
        "decor": {name: {**raw(DECOR[name]()), "wall": name in WALL_DECOR} for name in decor},
    }


def build() -> dict[str, list[dict]]:
    sets = []

    sets.append(theme("town_street", "городская улица: брусчатка, фонари, бочки", "outdoor", {
        "floor": surface(stones("q", "ts"), "Q", 1),
        "fill": speckle(tile().rect(0, 0, 15, 15, "g"), "g", "G", 0.25, "tsf"),
        "slab": planks("p", 4),
        "edge": bricks("q"),
        "ladder": ladder("p"),
        "door": door("p", "q", "closed"), "door_open": door("p", "q", "open"), "door_locked": door("p", "q", "locked"),
    }, ["lamp_post", "barrel", "crate", "sign", "bench"]))

    sets.append(theme("house_interior", "жилой дом: деревянный пол, обои, картины", "indoor", {
        "floor": planks("p", 4, 3),
        "fill": planks("P", 8, 5),
        "slab": surface(planks("p", 4, 1), "P", 1),
        "wall": tile().rect(0, 0, 15, 15, "f").vline(3, 0, 15, "F").vline(11, 0, 15, "F"),
        "edge": planks("P", 16).vline(15, 0, 15, "o"),
        "ladder": ladder("p"),
        "door": door("p", "P", "closed"), "door_open": door("p", "P", "open"), "door_locked": door("p", "P", "locked"),
    }, ["window", "picture", "shelf", "plant", "clock"]))

    sets.append(theme("tavern", "таверна: тёмные доски, камин, бочки", "indoor", {
        "floor": planks("P", 4, 2),
        "fill": planks("P", 8),
        "slab": surface(planks("p", 4), "P", 1),
        "wall": bricks("q", 4, 8),
        "edge": planks("p", 16),
        "ladder": ladder("p"),
        "door": door("p", "q", "closed"), "door_open": door("p", "q", "open"), "door_locked": door("p", "q", "locked"),
    }, ["barrel", "table_mug", "hearth", "banner", "crate"]))

    sets.append(theme("forest", "лес: трава, земля, деревья и грибы", "outdoor", {
        "floor": speckle(surface(tile().rect(0, 0, 15, 15, "g"), "v", 3), "g", "G", 0.2, "ff").rect(0, 3, 15, 3, "V"),
        "fill": speckle(tile().rect(0, 0, 15, 15, "g"), "g", "G", 0.3, "ffill"),
        "slab": tile().rect(0, 1, 15, 4, "p").hline(0, 15, 4, "P").set(5, 2, "P").set(12, 3, "P"),
        "edge": tile().rect(4, 0, 11, 15, "p").vline(6, 0, 15, "P").vline(10, 0, 15, "P"),
        "ladder": ladder("p"),
        "door": door("p", "q", "closed"), "door_open": door("p", "q", "open"), "door_locked": door("p", "q", "locked"),
    }, ["tree", "bush", "mushroom", "rock", "flowers"]))

    sets.append(theme("cave", "пещера: камень, сталагмиты, светящиеся кристаллы", "indoor", {
        "floor": surface(stones("q", "cv"), "q", 1),
        "fill": speckle(tile().rect(0, 0, 15, 15, "F"), "F", "f", 0.2, "cvf"),
        "slab": stones("q", "cvs").clear(lambda x, y: y > 6),
        "wall": speckle(tile().rect(0, 0, 15, 15, "F"), "F", "k", 0.12, "cvw"),
        "edge": stones("q", "cve"),
        "ladder": ladder("p"),
        "door": door("p", "Q", "closed"), "door_open": door("p", "Q", "open"), "door_locked": door("p", "Q", "locked"),
    }, ["stalagmite", "crystal", "bones", "mushroom", "rock"]))

    sets.append(theme("castle", "замок или башня: каменные плиты, факелы, знамёна", "indoor", {
        "floor": surface(bricks("q", 8, 16), "Q", 1),
        "fill": bricks("Q", 8, 16),
        "slab": surface(bricks("q", 8, 8), "Q", 1),
        "wall": bricks("q", 4, 8),
        "edge": bricks("q", 8, 16).vline(0, 0, 15, "Q").vline(15, 0, 15, "Q"),
        "ladder": ladder("p"),
        "door": door("p", "q", "closed").hline(3, 12, 12, "m").hline(3, 12, 24, "m"),
        "door_open": door("p", "q", "open"),
        "door_locked": door("p", "q", "locked").hline(3, 12, 12, "m").hline(3, 12, 24, "m"),
    }, ["torch", "banner", "armor_stand", "slit_window"]))

    sets.append(theme("office", "контора или участок: плитка, столы, шкафы", "indoor", {
        "floor": tile().rect(0, 0, 15, 15, "q").rect(0, 0, 7, 7, "Q").rect(8, 8, 15, 15, "Q"),
        "fill": speckle(tile().rect(0, 0, 15, 15, "Q"), "Q", "q", 0.15, "of"),
        "slab": surface(tile().rect(0, 0, 15, 15, "q"), "Q", 2),
        "wall": tile().rect(0, 0, 15, 15, "f").hline(0, 15, 15, "F"),
        "edge": tile().rect(0, 0, 15, 15, "F").vline(15, 0, 15, "o"),
        "ladder": ladder("m"),
        "door": door("p", "F", "closed").rect(6, 9, 9, 13, "n"),
        "door_open": door("p", "F", "open"),
        "door_locked": door("p", "F", "locked").rect(6, 9, 9, 13, "n"),
    }, ["desk", "cabinet", "plant", "poster", "cooler"]))

    sets.append(theme("ship", "корабль или станция: металл, трубы, пульты", "indoor", {
        "floor": surface(tile().rect(0, 0, 15, 15, "m").hline(0, 15, 4, "M").vline(8, 5, 15, "M"), "M", 1),
        "fill": tile().rect(0, 0, 15, 15, "M"),
        "slab": tile().rect(0, 0, 15, 3, "m").hline(0, 15, 3, "M").set(2, 1, "o").set(13, 1, "o"),
        "wall": tile().rect(0, 0, 15, 15, "q").hline(0, 15, 0, "Q").vline(0, 0, 15, "Q").set(2, 2, "o").set(13, 2, "o").set(2, 13, "o").set(13, 13, "o"),
        "edge": tile().rect(0, 0, 15, 15, "m").vline(3, 0, 15, "M").vline(12, 0, 15, "M"),
        "ladder": ladder("m"),
        "door": tall().rect(1, 4, 14, 31, "m").rect(3, 6, 12, 31, "q").vline(7, 6, 31, "Q").set(13, 8, "l"),
        "door_open": tall().rect(1, 4, 14, 31, "m").rect(3, 6, 12, 31, "k").set(13, 8, "l"),
        "door_locked": tall().rect(1, 4, 14, 31, "m").rect(3, 6, 12, 31, "q").vline(7, 6, 31, "Q").set(13, 8, "a").rect(6, 16, 9, 19, "a"),
    }, ["pipes", "console", "crate", "porthole", "vent"]))
    return {"tileset": sets}
