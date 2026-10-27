"""Слои фона 160×90 (SPEC §5.7.4).

Небо, дальний план и земля рисуются на полном холсте (anchor относительно
(0, 0)). Предмет рисуется на своём холсте вокруг точки основания PROP_REF;
рендер ставит её в (x, PROP_BASE_Y).

Буквы — слоты настроенческой палитры: f/F дальний план, g/G земля,
p/P дерево, q/Q камень, v/V зелень, a/A акцент, l — свет (не тонируется
временем суток), n/N — светлый тон неба (вычисляется из градиента неба),
плюс фиксированные o, k, w, m.
"""

from __future__ import annotations

import math
import random

from px import T, Grid

W, H = 160, 90
HORIZON = 72          # нижний край дальнего плана, верх земли
PROP_BASE_Y = 82      # куда ставится основание предмета
PROP_W, PROP_H = 80, 80
PROP_REF = (40, 79)


def full() -> Grid:
    return Grid(W, H)


def full_part(id: str, slot: str, description: str, g: Grid, **extra) -> dict:
    return {"id": id, "slot": slot, "description": description, **g.sprite((0, 0)), **extra}


# --- небо ----------------------------------------------------------------------

def sky_part(id: str, description: str, g: Grid | None = None, **extra) -> dict:
    g = g or full()
    return full_part(id, "sky", description, g, **extra)


def cloud(g: Grid, x: int, y: int, scale: float = 1.0, c: str = "n") -> None:
    for dx, dy, r in [(0, 0, 4), (5, -2, 5), (11, 0, 4), (6, 2, 4), (-4, 2, 3), (15, 2, 3)]:
        g.ellipse(x + dx * scale, y + dy * scale, r * scale * 1.3, r * scale * 0.8, c)
    g.shade(c, "down", 1)


def skies() -> list[dict]:
    sun = full().ellipse(124, 18, 7, 7, "l")
    moon = full().ellipse(126, 16, 6, 6, "w")
    moon.ellipse(129, 14, 5, 5, T, over="w")
    clouds = full()
    for x, y, s in [(14, 14, 1.0), (62, 24, 0.8), (104, 10, 1.2), (140, 30, 0.7)]:
        cloud(clouds, x, y, s)
    storm = full()
    for x in range(-6, 166, 14):
        cloud(storm, x, 6 + (x * 7) % 9, 1.4, "N")
    for x in range(4, 160, 18):
        cloud(storm, x, 20 + (x * 5) % 7, 1.0, "N")
    return [
        sky_part("clear", "чистое небо, только градиент"),
        sky_part("sun", "яркое солнце (для дня и заката)", sun),
        sky_part("moon", "месяц и звёзды (для ночи)", moon, stars=40),
        sky_part("stars", "звёздное небо без луны", stars=90),
        sky_part("clouds", "небо с несколькими облаками", clouds),
        sky_part("storm", "тяжёлые грозовые тучи", storm),
    ]


# --- дальний план -----------------------------------------------------------------

def far_part(id: str, description: str, g: Grid, setting: str) -> dict:
    return full_part(id, "far", description, g, setting=setting)


def city() -> Grid:
    rng = random.Random("city")
    g = full()
    x = 0
    while x < W:
        w = rng.randint(6, 12)
        g.rect(x, HORIZON - rng.randint(30, 46), x + w, HORIZON, "F")
        x += w + rng.randint(-2, 1)
    x = -3
    while x < W:
        w = rng.randint(9, 17)
        h = rng.randint(16, 34)
        top = HORIZON - h
        g.rect(x, top, x + w, HORIZON, "f")
        if rng.random() < 0.4:
            g.poly([(x - 0.5, top + 0.5), (x + w / 2 + 0.5, top - 6), (x + w + 1.5, top + 0.5)], "f")
        for wy in range(top + 3, HORIZON - 3, 4):
            for wx in range(x + 2, x + w - 1, 3):
                if rng.random() < 0.35:
                    g.rect(wx, wy, wx + 1, wy + 1, "l")
        x += w + rng.randint(0, 2)
    g.shade("f", "right", 1)
    return g


def mountains() -> Grid:
    g = full()
    back = lambda x: HORIZON - 34 - 14 * math.sin(x / 23) - 8 * math.sin(x / 9 + 1)
    front = lambda x: HORIZON - 16 - 9 * math.sin(x / 17 + 2) - 5 * math.sin(x / 6)
    g.fill(lambda x, y: back(x) <= y <= HORIZON, "f")
    g.fill(lambda x, y: back(x) <= y <= back(x) + 2 + max(0, HORIZON - 42 - back(x)) and back(x) < HORIZON - 42, "n")
    g.fill(lambda x, y: front(x) <= y <= HORIZON, "F")
    return g


def forest() -> Grid:
    rng = random.Random("forest")
    g = full()
    for row, (c, base, hmin, hmax) in enumerate([("V", HORIZON - 6, 22, 34), ("v", HORIZON, 16, 28)]):
        x = -4 + row * 5
        while x < W + 4:
            h = rng.randint(hmin, hmax)
            g.poly([(x - 6, base), (x + 0.5, base - h), (x + 7, base)], c)
            x += rng.randint(6, 10)
    g.rect(0, HORIZON - 6, W, HORIZON, "V", over=T)
    g.shade("v", "right", 1)
    return g


def sea_cliffs() -> Grid:
    g = full()
    g.rect(0, HORIZON - 14, W, HORIZON, "f")
    for y in range(HORIZON - 13, HORIZON, 3):
        for x in range((y * 7) % 11, W, 13):
            g.hline(x, x + 4, y, "n")
    cliff = lambda x: HORIZON - 30 + 0.35 * x + 3 * math.sin(x / 5)
    g.fill(lambda x, y: x < 70 and y >= cliff(x), "F")
    base = int(cliff(16.5)) + 1  # маяк стоит на утёсе
    g.rect(14, base - 20, 19, base, "w").rect(13, base - 23, 20, base - 20, "a")
    g.rect(15, base - 22, 18, base - 21, "l")
    for y in range(base - 18, base - 1, 5):
        g.hline(14, 19, y, "a")
    return g


def house(g: Grid, x: int, w: int, h: int, roof: int) -> None:
    top = HORIZON - h
    g.rect(x, top, x + w, HORIZON, "q")
    g.poly([(x - 2, top + 0.5), (x + w / 2 + 0.5, top - roof), (x + w + 3, top + 0.5)], "p")
    g.rect(x + 2, top + 3, x + 3, top + 4, "l")
    if w > 8:
        g.rect(x + w - 4, top + 3, x + w - 3, top + 4, "l")
    g.rect(x + w // 2, HORIZON - 5, x + w // 2 + 1, HORIZON, "P")


def village() -> Grid:
    g = full()
    rng = random.Random("village")
    for x in range(0, W, 9):
        g.ellipse(x + 4, HORIZON - 6, 6, 8, "V")
    x = 2
    while x < W:
        w = rng.randint(8, 13)
        house(g, x, w, rng.randint(9, 14), rng.randint(5, 8))
        x += w + rng.randint(5, 12)
    g.shade("q", "right", 1).shade("p", "right", 1)
    return g


def castle() -> Grid:
    g = full()
    g.ellipse(80, HORIZON + 4, 90, 12, "F")
    g.rect(40, HORIZON - 24, 120, HORIZON, "q")
    for x in range(40, 121, 4):
        g.rect(x, HORIZON - 27, x + 1, HORIZON - 24, "q")
    for tx, th in ((36, 40), (76, 50), (116, 40)):
        g.rect(tx, HORIZON - th, tx + 9, HORIZON, "q")
        g.poly([(tx - 1.5, HORIZON - th + 0.5), (tx + 5, HORIZON - th - 10), (tx + 11.5, HORIZON - th + 0.5)], "a")
        g.rect(tx + 4, HORIZON - th + 6, tx + 5, HORIZON - th + 8, "l")
    g.rect(76, HORIZON - 10, 84, HORIZON, "k")
    g.ellipse(80, HORIZON - 10, 4, 3, "k")
    g.shade("q", "right", 1).shade("a", "right", 1)
    return g


def ruins() -> Grid:
    g = full()
    for i, (x, h) in enumerate([(8, 30), (30, 18), (52, 36), (96, 26), (118, 34), (142, 14)]):
        g.rect(x, HORIZON - h, x + 6, HORIZON, "q").rect(x - 1, HORIZON - h - 2, x + 7, HORIZON - h, "q")
        g.clear(lambda px_, py_, x=x, h=h, i=i: py_ < HORIZON - h + 3 and x + 2 + i % 3 < px_ <= x + 8)
    g.fill(lambda x, y: 52 <= x <= 103 and HORIZON - 40 <= y <= HORIZON - 34 and not (60 < x < 96 and y > HORIZON - 36), "q")
    g.fill(lambda x, y: 60 <= x <= 96 and ((x - 78) / 18) ** 2 + ((y - (HORIZON - 34)) / 6) ** 2 <= 1 and ((x - 78) / 15) ** 2 + ((y - (HORIZON - 34)) / 4) ** 2 > 1 and y >= HORIZON - 34, "q")
    for x, y in [(10, 50), (54, 44), (120, 46), (98, 54), (32, 60)]:
        g.vline(x, y, y + 10, "v").set(x + 1, y + 3, "v").set(x - 1, y + 7, "v")
    g.shade("q", "right", 1)
    return g


def room_wall() -> Grid:
    g = full()
    g.rect(0, 0, W, HORIZON, "f")
    g.dither("f", "F", 0)
    g.replace("F", "f")
    for x in range(0, W, 8):
        g.vline(x, 0, 50, "F")
    g.rect(0, 50, W, HORIZON, "p")
    g.hline(0, W, 50, "P").hline(0, W, 51, "o")
    for x in range(6, W, 20):
        g.rect(x, 55, x + 12, 68, "P").rect(x + 1, 56, x + 11, 67, "p")
    g.hline(0, W, HORIZON - 1, "P")
    return g


def cave() -> Grid:
    rng = random.Random("cave")
    g = full()
    g.rect(0, 0, W, HORIZON, "F")
    for _ in range(40):
        g.ellipse(rng.randint(0, W), rng.randint(0, HORIZON), rng.randint(4, 12), rng.randint(3, 7), "f")
    x = 0
    while x < W:
        w, h = rng.randint(4, 8), rng.randint(6, 20)
        g.poly([(x, -0.5), (x + w / 2, h), (x + w, -0.5)], "k")
        x += w + rng.randint(2, 10)
    for x, y in [(22, 60), (90, 64), (140, 58)]:
        g.poly([(x, y + 6), (x + 2, y), (x + 4, y + 6)], "l").poly([(x + 3, y + 6), (x + 6, y + 2), (x + 7, y + 6)], "l")
    g.fill(lambda x, y: min(x, W - x) < 6 + 4 * math.sin(y / 5), "k")
    return g


def spaceship() -> Grid:
    g = full()
    g.rect(0, 0, W, HORIZON, "q")
    for x in range(0, W, 20):
        g.vline(x, 0, HORIZON, "Q")
    for y in (14, 52):
        g.hline(0, W, y, "Q")
    g.rect(0, 0, W, 5, "m").hline(0, W, 5, "o")
    for cx in (40, 120):
        g.ellipse(cx, 30, 11, 11, "m")
        g.ellipse(cx, 30, 9, 9, "k")
        for dx, dy in [(-4, -3), (3, 2), (-1, 5), (5, -5)]:
            g.set(cx + dx, 30 + dy, "w")
    for x in range(6, W, 20):
        g.rect(x, 58, x + 7, 63, "o")
        g.set(x + 1, 59, "l").set(x + 3, 60, "a").set(x + 5, 59, "l")
    g.hline(0, W, 66, "m").hline(0, W, 68, "m")
    return g


FAR = [
    ("city", "город: силуэты домов с горящими окнами", city, "outdoor"),
    ("mountains", "горная гряда со снежными вершинами", mountains, "outdoor"),
    ("forest", "стена хвойного леса", forest, "outdoor"),
    ("sea_cliffs", "море и прибрежные утёсы с маяком", sea_cliffs, "outdoor"),
    ("village", "деревня: домики с крышами", village, "outdoor"),
    ("castle", "замок на холме", castle, "outdoor"),
    ("ruins", "руины: колонны и разрушенная арка", ruins, "outdoor"),
    ("room_wall", "стена комнаты: обои и деревянные панели", room_wall, "indoor"),
    ("cave", "пещера: каменные стены и сталактиты", cave, "indoor"),
    ("spaceship", "отсек космического корабля с иллюминаторами", spaceship, "indoor"),
]


# --- земля -------------------------------------------------------------------------

def ground_grid() -> Grid:
    return full().rect(0, HORIZON, W - 1, H - 1, "g")


def grounds() -> list[dict]:
    rng = random.Random("ground")
    cobble = ground_grid()
    for row, y in enumerate(range(HORIZON + 1, H, 4)):
        for x in range(-(row % 2) * 4, W, 8):
            cobble.ellipse(x + 4, y + 1.5, 3.6, 1.8, "G")
            cobble.ellipse(x + 3.5, y + 1, 2.8, 1.2, "g")
    cobble.hline(0, W, HORIZON, "G")

    planks = full().rect(0, HORIZON, W - 1, H - 1, "p")
    for row, y in enumerate(range(HORIZON, H, 4)):
        planks.hline(0, W, y, "P")
        for x in range((row * 13) % 30, W, 30):
            planks.vline(x, y, y + 3, "P")

    grass = ground_grid().replace("g", "v")
    for x in range(0, W):
        if rng.random() < 0.5:
            grass.vline(x, HORIZON - rng.randint(1, 2), HORIZON, "v")
    for _ in range(140):
        grass.set(rng.randint(0, W), rng.randint(HORIZON + 2, H), "V")

    rock = ground_grid()
    for _ in range(14):
        x, y = rng.randint(0, W), rng.randint(HORIZON + 2, H - 2)
        rock.line(x, y, x + rng.randint(-6, 6), y + rng.randint(1, 4), "G")
    for _ in range(24):
        rock.ellipse(rng.randint(0, W), rng.randint(HORIZON + 2, H), 1.6, 1.0, "q")
    rock.hline(0, W, HORIZON, "G")

    metal = full().rect(0, HORIZON, W - 1, H - 1, "m")
    for y in range(HORIZON, H, 6):
        metal.hline(0, W, y, "M")
    for x in range(0, W, 16):
        metal.vline(x, HORIZON, H, "M")
        for y in range(HORIZON + 2, H, 6):
            metal.set(x + 2, y, "o").set(x + 13, y, "o")

    dirt = ground_grid()
    for _ in range(200):
        dirt.set(rng.randint(0, W), rng.randint(HORIZON, H), "G")
    for _ in range(18):
        dirt.ellipse(rng.randint(0, W), rng.randint(HORIZON + 2, H), 1.4, 0.9, "q")

    def gp(id, description, g):
        return full_part(id, "ground", description, g)

    return [
        gp("cobblestone", "брусчатка", cobble),
        gp("planks", "деревянный пол из досок", planks),
        gp("grass", "трава", grass),
        gp("rock", "каменистая земля", rock),
        gp("metal", "металлический настил с заклёпками", metal),
        gp("dirt", "утоптанная земля, песок или снег (по палитре)", dirt),
    ]


# --- предметы ----------------------------------------------------------------------

def pg() -> Grid:
    return Grid(PROP_W, PROP_H)


B = PROP_REF[1]  # нижняя строка (основание)
C = PROP_REF[0]


def prop(id: str, description: str, g: Grid, setting: str = "any") -> dict:
    return {"id": id, "slot": "prop", "description": description, "setting": setting, **g.sprite(PROP_REF)}


def props() -> list[dict]:
    out = []

    g = pg().rect(C - 7, B - 33, C + 7, B, "p")
    g.ellipse(C, B - 33, 7.5, 4, "p")
    g.outline()
    g.vline(C, B - 34, B, "P").set(C + 4, B - 16, "m")
    out.append(prop("door", "деревянная дверь", g.shade("p", "right", 1)))

    g = pg().rect(C - 8, B - 50, C + 8, B - 32, "p")
    g.rect(C - 6, B - 48, C + 6, B - 34, "n").vline(C, B - 48, B - 34, "p").hline(C - 6, C + 6, B - 41, "p")
    g.outline()
    out.append(prop("window", "окно на стене", g, "indoor"))

    g = pg().rect(C - 14, B - 13, C + 14, B - 11, "p").rect(C - 12, B - 10, C - 11, B, "p").rect(C + 11, B - 10, C + 12, B, "p")
    g.outline().shade("p", "down", 1)
    out.append(prop("table", "деревянный стол", g))

    g = pg().rect(C - 4, B - 8, C + 4, B - 7, "p").rect(C + 3, B - 20, C + 4, B - 8, "p")
    g.rect(C - 4, B - 6, C - 3, B, "p").rect(C + 3, B - 6, C + 4, B, "p")
    g.outline()
    out.append(prop("chair", "стул", g))

    g = pg().rect(C - 12, B - 40, C + 12, B, "p")
    for y in range(B - 37, B - 2, 9):
        g.rect(C - 10, y, C + 10, y + 6, "k")
        x = C - 10
        rng = random.Random(y)
        while x < C + 10:
            w = rng.randint(1, 3)
            g.rect(x, y + rng.randint(0, 2), x + w - 1, y + 6, rng.choice("aqvfP"))
            x += w + 1
    g.outline()
    out.append(prop("bookshelf", "книжный шкаф", g.shade("p", "right", 1), "indoor"))

    g = pg().rect(C - 1, B - 22, C, B, "m").rect(C - 5, B - 1, C + 5, B, "m").rect(C - 7, B - 22, C + 7, B - 21, "m")
    for x in (C - 7, C, C + 6):
        g.rect(x, B - 26, x + 1, B - 23, "w").set(x, B - 28, "l").set(x + 1, B - 27, "l")
    g.outline()
    out.append(prop("candelabra", "канделябр со свечами", g))

    g = pg().rect(C - 1, B - 40, C, B, "o").rect(C - 3, B - 2, C + 2, B, "o")
    g.rect(C - 4, B - 46, C + 3, B - 40, "l").rect(C - 5, B - 47, C + 4, B - 47, "o").rect(C - 4, B - 39, C + 3, B - 39, "o")
    out.append(prop("lamp_post", "уличный фонарь", g, "outdoor"))

    g = pg().rect(C - 2, B - 22, C + 2, B, "p")
    for dx, dy, r in [(0, -40, 13), (-9, -30, 10), (9, -31, 10), (0, -26, 10)]:
        g.ellipse(C + dx, B + dy, r, r * 0.85, "v")
    g.outline().shade("v", "right", 3).shade("p", "right", 1)
    out.append(prop("tree", "лиственное дерево", g, "outdoor"))

    g = pg().rect(C - 1, B - 8, C + 1, B, "p")
    for i, y in enumerate(range(B - 56, B - 8, 10)):
        g.poly([(C - 5 - i * 2.5, y + 14), (C + 0.5, y), (C + 6 + i * 2.5, y + 14)], "v")
    g.outline().shade("v", "right", 2)
    out.append(prop("pine", "ель", g, "outdoor"))

    g = pg()
    for dx, r in [(-6, 6), (0, 8), (7, 6)]:
        g.ellipse(C + dx, B - r * 0.8, r, r * 0.8, "v")
    g.outline().shade("v", "right", 2)
    out.append(prop("bush", "куст", g, "outdoor"))

    g = pg().ellipse(C, B - 6, 11, 7, "q").ellipse(C + 7, B - 3, 6, 4, "q")
    g.clear(lambda x, y: y > B + 1)
    g.outline().shade("q", "right", 3).shade("q", "down", 1)
    out.append(prop("boulder", "валун", g, "outdoor"))

    g = pg()
    for x0, y0, s in [(C - 12, B - 11, 11), (C, B - 9, 9), (C - 7, B - 21, 9)]:
        g.rect(x0, y0, x0 + s, y0 + s, "p")
        g.line(x0, y0, x0 + s, y0 + s, "P").hline(x0, x0 + s, y0, "P")
    g.outline()
    out.append(prop("crates", "штабель ящиков", g))

    g = pg().ellipse(C, B - 8, 7, 9, "p")
    g.clear(lambda x, y: y > B + 1 or y < B - 16)
    g.hline(C - 6, C + 6, B - 13, "m").hline(C - 6, C + 6, B - 3, "m")
    g.outline().shade("p", "right", 2)
    out.append(prop("barrel", "бочка", g))

    g = pg().rect(C - 9, B - 9, C + 9, B, "p").ellipse(C, B - 9, 9.5, 4, "p")
    g.clear(lambda x, y: y < B - 13)
    g.hline(C - 9, C + 9, B - 8, "m").rect(C - 1, B - 9, C + 1, B - 6, "a")
    g.outline().shade("p", "right", 1)
    out.append(prop("chest", "сундук", g))

    g = pg()
    for x in range(C - 18, C + 19, 6):
        g.rect(x, B - 12, x + 1, B, "p").set(x, B - 13, "p")
    g.hline(C - 18, C + 19, B - 9, "p").hline(C - 18, C + 19, B - 4, "p")
    g.outline()
    out.append(prop("fence", "деревянный забор", g, "outdoor"))

    g = pg().rect(C - 9, B - 10, C + 9, B, "q").ellipse(C, B - 10, 9, 2.5, "k")
    g.rect(C - 9, B - 26, C - 8, B - 10, "p").rect(C + 8, B - 26, C + 9, B - 10, "p").poly([(C - 12, B - 25), (C + 0.5, B - 33), (C + 13, B - 25)], "a")
    g.vline(C, B - 25, B - 14, "o").rect(C - 1, B - 14, C + 1, B - 12, "p")
    g.outline().shade("q", "right", 1)
    for y in range(B - 8, B, 3):
        g.hline(C - 8, C + 8, y, "Q")
    out.append(prop("well", "колодец с крышей", g, "outdoor"))

    g = pg().rect(C - 1, B - 28, C, B, "p").rect(C - 9, B - 26, C + 9, B - 21, "p").poly([(C + 9, B - 26), (C + 13, B - 23.5), (C + 9, B - 21)], "p")
    g.hline(C - 7, C + 7, B - 24, "P")
    g.outline()
    out.append(prop("signpost", "указатель на столбе", g, "outdoor"))

    g = pg()
    g.line(C - 8, B, C + 7, B - 4, "p").line(C - 7, B - 4, C + 8, B, "p")
    g.poly([(C - 6, B - 2), (C - 3, B - 12), (C, B - 6), (C + 2, B - 16), (C + 5, B - 5), (C + 6, B - 2)], "l")
    g.poly([(C - 3, B - 2), (C, B - 8), (C + 3, B - 2)], "w")
    out.append(prop("campfire", "костёр", g, "outdoor"))

    g = pg().rect(C - 8, B - 6, C + 8, B, "q")
    g.ellipse(C, B - 30, 4, 4, "q").rect(C - 4, B - 26, C + 4, B - 7, "q").rect(C - 7, B - 24, C - 5, B - 14, "q").rect(C + 5, B - 24, C + 7, B - 14, "q")
    g.outline().shade("q", "right", 2)
    out.append(prop("statue", "каменная статуя на постаменте", g))

    g = pg().rect(C - 5, B - 44, C + 5, B, "q").rect(C - 7, B - 47, C + 7, B - 44, "q").rect(C - 7, B - 3, C + 7, B, "q")
    for x in range(C - 3, C + 4, 3):
        g.vline(x, B - 43, B - 4, "Q")
    g.outline().shade("q", "right", 1)
    out.append(prop("pillar", "колонна", g))

    g = pg().rect(C - 9, B - 34, C + 9, B - 12, "a").rect(C - 11, B - 14, C + 11, B - 10, "a").rect(C - 11, B - 10, C - 9, B, "m").rect(C + 9, B - 10, C + 11, B, "m")
    g.poly([(C - 9, B - 34), (C + 0.5, B - 40), (C + 10, B - 34)], "m")
    g.outline().shade("a", "right", 2)
    g.set(C, B - 37, "l")
    out.append(prop("throne", "трон", g, "indoor"))

    g = pg().ellipse(C, B - 7, 10, 7, "k")
    g.clear(lambda x, y: y < B - 10)
    g.ellipse(C, B - 10, 9, 2, "a")
    for x, y in [(C - 3, B - 15), (C + 2, B - 18), (C, B - 21)]:
        g.ellipse(x, y, 1.6, 1.6, "a")
    g.outline()
    out.append(prop("cauldron", "котёл с бурлящим зельем", g))

    g = pg().rect(C - 12, B - 16, C + 12, B, "q").poly([(C - 12, B - 16), (C - 9, B - 22), (C + 9, B - 22), (C + 12, B - 16)], "m")
    g.rect(C - 8, B - 21, C + 8, B - 18, "k")
    for i, x in enumerate(range(C - 7, C + 8, 3)):
        g.set(x, B - 20, "la"[i % 2])
    g.rect(C - 9, B - 12, C - 5, B - 8, "o").set(C - 7, B - 10, "l")
    g.outline()
    out.append(prop("console", "пульт управления со светящимися кнопками", g, "indoor"))

    g = pg().rect(C - 6, B - 14, C + 6, B, "q").ellipse(C, B - 14, 6, 5, "q")
    g.vline(C, B - 16, B - 7, "Q").hline(C - 3, C + 3, B - 13, "Q")
    g.outline().shade("q", "right", 1)
    out.append(prop("gravestone", "надгробие", g, "outdoor"))

    g = pg().rect(C - 1, B - 50, C, B, "p").rect(C + 1, B - 48, C + 12, B - 30, "a")
    g.poly([(C + 1, B - 30), (C + 6.5, B - 26), (C + 13, B - 30)], "a")
    g.ellipse(C + 7, B - 40, 3, 3, "l")
    g.outline().shade("a", "right", 1)
    out.append(prop("banner", "знамя на древке", g))

    return out


def build() -> dict[str, list[dict]]:
    return {
        "sky": skies(),
        "far": [far_part(id, d, fn(), s) for id, d, fn, s in FAR],
        "ground": grounds(),
        "prop": props(),
    }
