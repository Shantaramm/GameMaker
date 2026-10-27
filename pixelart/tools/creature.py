"""Существа 64×64 (SPEC §5.7.3).

Тело рисуется на полном холсте и ставится anchor-ом в REF. Точки крепления
(`points`) хранятся в координатах спрайта тела. Особенность рисуется вокруг
точки REF своего холста: её anchor — это пиксель, который встаёт на точку
крепления тела (`attach`). `layer: back` рисуется до тела.

Цвета: c/C — основной цвет, a/A — акцент, e — глаза (светлый акцент),
w, k, o, m — фиксированные.
"""

from __future__ import annotations

import math

from px import T, Grid

W = H = 64
REF = (32, 32)


def grid() -> Grid:
    return Grid(W, H)


FACING_LEFT = {"wolf", "dragonling", "rat"}  # нарисованы в профиль мордой влево


def body_part(id: str, description: str, g: Grid, points: dict[str, tuple[int, int]]) -> dict:
    sprite = g.sprite(REF)
    ox, oy = REF[0] - sprite["anchor"][0], REF[1] - sprite["anchor"][1]
    local = {k: [x - ox, y - oy] for k, (x, y) in points.items()}
    faces = "left" if id in FACING_LEFT else "front"
    return {"id": id, "slot": "creature_body", "description": description, **sprite, "points": local, "faces": faces}


def finish(g: Grid, shade_width: int = 2) -> Grid:
    g.outline()
    g.shade("c", "right", shade_width).shade("a", "right", 1)
    return g


def eye(g: Grid, x: int, y: int, size: int = 2) -> None:
    g.rect(x, y, x + size - 1, y + size - 1, "e")
    g.set(x, y, "w")


# --- тела ----------------------------------------------------------------------

def slime() -> dict:
    g = grid()
    g.fill(lambda x, y: ((x - 32) / 16) ** 2 + ((y - 50) / 13) ** 2 <= 1 and y < 59.5, "c")
    g.ellipse(32, 38, 5, 4, "c")
    g.ellipse(38, 52, 4, 3, "a")
    finish(g, 3)
    g.rect(24, 41, 26, 43, "w").rect(23, 44, 24, 45, "w")
    for x in (27, 35):
        g.rect(x, 46, x + 2, 49, "k").set(x, 46, "w")
    g.hline(29, 34, 53, "k")
    return body_part("slime", "слизень: желейная капля с глазами", g,
                     {"head_top": (32, 35), "back": (44, 44), "face": (32, 47), "mouth": (32, 53)})


def wolf() -> dict:
    g = grid()
    g.ellipse(38, 45, 13, 8, "c")
    for x in (28, 33, 42, 47):
        g.rect(x - 1, 50, x + 1, 59, "c")
    g.poly([(49, 42), (58, 34), (60, 37), (52, 46)], "c")  # хвост
    g.ellipse(22, 37, 7.5, 6.5, "c")
    g.poly([(16, 36), (8, 39), (8, 42), (18, 43)], "c")  # морда
    g.poly([(17, 32), (18, 24), (22, 31)], "c").poly([(23, 31), (26, 24), (28, 32)], "c")  # уши
    g.fill(lambda x, y: ((x - 26) / 6) ** 2 + ((y - 47) / 6) ** 2 <= 1, "a", over="c")  # грудь
    finish(g)
    eye(g, 19, 35)
    g.rect(7, 39, 8, 40, "k")
    g.hline(10, 16, 43, "o")
    g.set(12, 44, "w").set(15, 44, "w")
    return body_part("wolf", "волк: поджарый зверь в профиль", g,
                     {"head_top": (22, 28), "back": (40, 38), "face": (20, 35), "mouth": (12, 43)})


def skeleton() -> dict:
    g = grid()
    g.ellipse(32, 19, 6.5, 7, "c")
    g.rect(28, 24, 36, 28, "c")  # челюсть
    g.rect(31, 28, 33, 44, "c")  # позвоночник
    for y in (31, 34, 37):
        g.rect(24, y, 40, y + 1, "c")
    g.ellipse(32, 45, 7, 3, "c")  # таз
    g.line(24, 31, 18, 42, "c").line(23, 31, 17, 42, "c").line(40, 31, 46, 42, "c").line(41, 31, 47, 42, "c")
    g.line(28, 47, 26, 60, "c").line(29, 47, 27, 60, "c").line(36, 47, 38, 60, "c").line(35, 47, 37, 60, "c")
    finish(g, 1)
    for x in (28, 34):
        g.rect(x, 17, x + 2, 20, "k")
        g.set(x + 1, 18, "e")
    g.set(32, 22, "k")
    for x in range(29, 36, 2):
        g.set(x, 26, "k")
    return body_part("skeleton", "скелет: ходячие кости", g,
                     {"head_top": (32, 12), "back": (32, 32), "face": (32, 19), "mouth": (32, 26)})


def ghost() -> dict:
    g = grid()
    g.ellipse(32, 26, 12, 12, "c")
    g.rect(20, 26, 44, 52, "c")
    for i, x in enumerate(range(20, 45, 4)):
        g.ellipse(x + 2, 53, 2.2, 2.5 + (i % 2) * 1.5, "c")
    g.ellipse(17, 36, 3, 2.2, "c").ellipse(47, 34, 3, 2.2, "c")
    finish(g, 3)
    g.rect(23, 17, 25, 20, "w").set(24, 22, "w")
    for x in (26, 35):
        g.rect(x, 23, x + 2, 27, "k")
        g.set(x + 1, 25, "e")
    g.ellipse(32, 33, 2.2, 2.8, "k")
    return body_part("ghost", "призрак: парящий дух в саване", g,
                     {"head_top": (32, 14), "back": (32, 36), "face": (32, 25), "mouth": (32, 33)})


def golem() -> dict:
    g = grid()
    g.rect(19, 24, 44, 48, "c")
    g.ellipse(31, 24, 14, 5, "c")
    g.rect(26, 13, 37, 22, "c")
    g.rect(9, 26, 18, 50, "c").rect(45, 26, 54, 50, "c")  # руки
    g.rect(8, 48, 19, 54, "c").rect(44, 48, 55, 54, "c")  # кулаки
    g.rect(21, 48, 29, 60, "c").rect(34, 48, 42, 60, "c")
    finish(g, 3)
    g.hline(27, 36, 17, "e").hline(28, 35, 18, "e")
    g.line(23, 30, 29, 38, "C").line(29, 38, 26, 44, "C").line(39, 27, 36, 34, "C")
    g.line(12, 34, 15, 40, "C").line(49, 30, 51, 38, "C")
    g.hline(19, 44, 47, "o").vline(18, 26, 50, "o").vline(45, 26, 50, "o")
    for x0, y0 in ((20, 25), (38, 40), (46, 27), (27, 49)):
        g.rect(x0, y0, x0 + 3, y0 + 1, "a")
    return body_part("golem", "голем: каменный великан с мхом", g,
                     {"head_top": (32, 12), "back": (32, 25), "face": (32, 17), "mouth": (32, 20)})


def beetle() -> dict:
    g = grid()
    for i, y in enumerate((36, 42, 48)):
        g.line(20, y, 9, y + 5 - i * 2, "o").line(20, y + 1, 9, y + 6 - i * 2, "o")
        g.line(44, y, 55, y + 5 - i * 2, "o").line(44, y + 1, 55, y + 6 - i * 2, "o")
    g.ellipse(32, 44, 15, 14, "c")
    g.ellipse(32, 29, 8, 6, "c")
    g.poly([(26, 31), (21, 37), (25, 36)], "c").poly([(38, 31), (43, 37), (39, 36)], "c")  # жвалы
    finish(g, 3)
    g.vline(32, 33, 57, "o").vline(31, 33, 57, "o")
    for x, y in ((25, 42), (38, 46), (26, 51), (37, 39)):
        g.ellipse(x, y, 2.4, 2.2, "a", over="cC")
    eye(g, 27, 27)
    eye(g, 35, 27)
    g.rect(23, 37, 26, 39, "w")
    return body_part("beetle", "жук: панцирный гигант с жвалами", g,
                     {"head_top": (32, 23), "back": (32, 40), "face": (32, 28), "mouth": (32, 34)})


def robot() -> dict:
    g = grid()
    g.rect(25, 11, 38, 23, "m")
    g.rect(29, 24, 34, 26, "m")
    g.rect(21, 27, 42, 46, "c")
    g.rect(14, 28, 19, 44, "m").rect(44, 28, 49, 44, "m")
    g.rect(13, 45, 20, 49, "c").rect(43, 45, 50, 49, "c")
    g.rect(24, 47, 29, 59, "m").rect(34, 47, 39, 59, "m")
    g.rect(22, 59, 30, 61, "c").rect(33, 59, 41, 61, "c")
    g.outline()
    g.shade("m", "right", 2).shade("c", "right", 2)
    g.rect(27, 15, 36, 18, "k").hline(28, 35, 16, "e").hline(28, 35, 17, "e")
    g.rect(26, 31, 37, 39, "a").shade("a", "right", 1)
    g.rect(29, 33, 34, 37, "e").set(29, 33, "w")
    for x in (24, 39):
        g.set(x, 42, "e")
    g.hline(29, 34, 21, "k")
    return body_part("robot", "робот: железный механизм", g,
                     {"head_top": (32, 10), "back": (32, 30), "face": (32, 16), "mouth": (32, 21)})


def dragonling() -> dict:
    g = grid()
    g.poly([(42, 50), (54, 54), (60, 46), (57, 44), (53, 50), (44, 46)], "c")  # хвост
    g.ellipse(36, 45, 11, 11, "c")
    g.fill(lambda x, y: ((x - 33) / 6) ** 2 + ((y - 47) / 8) ** 2 <= 1, "a", over="c")  # брюхо
    for x in (29, 41):
        g.rect(x - 2, 52, x + 2, 59, "c")
    g.ellipse(22, 31, 7.5, 6.5, "c")
    g.poly([(16, 30), (8, 33), (9, 37), (18, 37)], "c")  # морда
    g.rect(24, 36, 30, 40, "c")  # шея
    finish(g, 2)
    g.shade("a", "right", 1)
    eye(g, 19, 29)
    g.set(9, 33, "k")
    g.hline(10, 17, 37, "o").set(13, 38, "w").set(16, 38, "w")
    for y in range(38, 54, 3):
        g.set(33, y, "A")
    return body_part("dragonling", "дракончик: маленький крылатый ящер", g,
                     {"head_top": (22, 25), "back": (40, 37), "face": (20, 29), "mouth": (11, 37)})


def shadow_cultist() -> dict:
    g = grid()
    g.poly([(32, 14), (48, 60), (16, 60)], "c")
    g.ellipse(32, 20, 9, 9, "c")
    g.poly([(20, 34), (12, 46), (17, 48), (24, 40)], "c").poly([(44, 34), (52, 46), (47, 48), (40, 40)], "c")
    finish(g, 3)
    g.ellipse(32, 22, 5.5, 6, "k")
    g.set(29, 21, "e").set(30, 21, "e").set(34, 21, "e").set(35, 21, "e")
    g.vline(32, 30, 59, "a").hline(17, 47, 59, "a")
    g.rect(12, 46, 15, 48, "C").rect(49, 46, 52, 48, "C")
    return body_part("shadow_cultist", "культист-тень: фигура в балахоне с горящими глазами", g,
                     {"head_top": (32, 11), "back": (32, 30), "face": (32, 21), "mouth": (32, 25)})


def rat() -> dict:
    g = grid()
    g.line(48, 50, 56, 44, "C").line(56, 44, 60, 47, "C").line(49, 51, 57, 45, "C")
    g.ellipse(37, 49, 13, 8, "c")
    g.ellipse(23, 45, 7, 6, "c")
    g.poly([(18, 43), (9, 47), (18, 50)], "c")
    g.ellipse(25, 38, 3.5, 3.5, "c")
    for x in (30, 44):
        g.rect(x - 1, 54, x + 1, 58, "c")
    g.fill(lambda x, y: ((x - 33) / 9) ** 2 + ((y - 54) / 3) ** 2 <= 1, "a", over="c")
    finish(g, 2)
    g.ellipse(25, 38, 1.6, 1.6, "a")
    eye(g, 20, 43)
    g.rect(9, 46, 10, 47, "k")
    g.set(12, 50, "w").set(13, 50, "w")
    return body_part("rat", "крыса-переросток", g,
                     {"head_top": (23, 37), "back": (38, 42), "face": (21, 44), "mouth": (12, 49)})


BODIES = [slime, wolf, skeleton, ghost, golem, beetle, robot, dragonling, shadow_cultist, rat]


# --- особенности ------------------------------------------------------------------

def feature(id: str, description: str, attach: str, g: Grid, layer: str = "front") -> dict:
    return {"id": id, "slot": "creature_feature", "description": description, "attach": attach, "layer": layer, **g.sprite(REF)}


def horns() -> dict:
    g = grid()
    for s in (-1, 1):
        g.poly([(32 + s * 3, 33), (32 + s * 7, 32), (32 + s * 9, 24), (32 + s * 6, 27)], "w")
    g.outline().shade("w", "down", 1)
    return feature("horns", "пара изогнутых рогов", "head_top", g)


def antlers() -> dict:
    g = grid()
    for s in (-1, 1):
        g.line(32 + s * 3, 32, 32 + s * 9, 22, "a").line(32 + s * 6, 27, 32 + s * 12, 25, "a")
        g.line(32 + s * 8, 24, 32 + s * 7, 18, "a").line(32 + s * 9, 22, 32 + s * 13, 19, "a")
    g.outline()
    return feature("antlers", "ветвистые оленьи рога", "head_top", g)


def unicorn_horn() -> dict:
    g = grid()
    g.poly([(30, 33), (34, 33), (32.5, 20)], "w")
    for y in (24, 27, 30):
        g.set(32, y, "a")
    g.outline()
    return feature("unicorn_horn", "единственный витой рог на лбу", "head_top", g)


def feather_wings() -> dict:
    g = grid()
    for s in (-1, 1):
        for i in range(4):
            g.ellipse(32 + s * (8 + i * 4), 26 + i * 3, 5, 9 - i, "w")
    g.outline().shade("w", "down", 2)
    return feature("feather_wings", "белые крылья с перьями", "back", g, layer="back")


def bat_wings() -> dict:
    g = grid()
    for s in (-1, 1):
        g.poly([(32, 30), (32 + s * 12, 14), (32 + s * 26, 20), (32 + s * 22, 30), (32 + s * 16, 28), (32 + s * 12, 36)], "a")
    g.outline()
    for s in (-1, 1):
        g.line(32 + s * 12, 15, 32 + s * 22, 29, "o").line(32 + s * 12, 15, 32 + s * 15, 28, "o")
    g.shade("a", "down", 1)
    return feature("bat_wings", "перепончатые крылья летучей мыши", "back", g, layer="back")


def third_eye() -> dict:
    g = grid()
    g.draw([".ooo.", "owewo", ".ooo."], 30, 25)
    return feature("third_eye", "третий глаз на лбу", "face", g)


def back_spikes() -> dict:
    g = grid()
    for i, x in enumerate(range(22, 43, 5)):
        g.poly([(x - 2.5, 34), (x, 34 - 6 - (i % 2) * 3), (x + 2.5, 34)], "a")
    g.outline().shade("a", "right", 1)
    return feature("back_spikes", "гребень шипов на спине", "back", g, layer="back")


def crown() -> dict:
    g = grid()
    g.rect(26, 29, 37, 32, "m")
    for x in (26, 31, 36):
        g.poly([(x - 0.5, 29.5), (x + 1, 25), (x + 2.5, 29.5)], "m")
    g.outline().shade("m", "right", 1)
    g.set(28, 31, "a").set(32, 31, "a").set(35, 31, "a")
    return feature("crown", "золотая корона", "head_top", g)


def halo() -> dict:
    g = grid()
    g.ellipse(32, 26, 8.5, 2.8, "w")
    g.outline()
    g.ellipse(32, 26, 5.2, 1.1, T)
    return feature("halo", "светящийся нимб над головой", "head_top", g, layer="back")


def fangs() -> dict:
    g = grid()
    g.draw(["w...w", "w...w", "W...W"], 30, 32)
    return feature("fangs", "торчащие клыки", "mouth", g)


FEATURES = [horns, antlers, unicorn_horn, feather_wings, bat_wings, third_eye, back_spikes, crown, halo, fangs]


def build() -> dict[str, list[dict]]:
    return {"body": [b() for b in BODIES], "feature": [f() for f in FEATURES]}
