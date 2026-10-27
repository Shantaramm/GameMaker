"""Иконки предметов 16×16 (SPEC §5.8.6).

c/C — цвет ценности предмета (value_tier → icon_tiers в palettes.json),
a/A — золото, p/P — дерево и кожа, v — зелень, r — красный,
m/M, w, k, o — фиксированные. Иконки не обрезаются (ровно 16×16).
"""

from __future__ import annotations

from px import T, Grid


def g16() -> Grid:
    return Grid(16, 16)


def fin(g: Grid, shade: str = "cpm") -> Grid:
    g.outline()
    for ch in shade:
        g.shade(ch, "right", 1)
    return g


def blade(g: Grid, x0: int, y0: int, x1: int, y1: int, c: str = "m", w: int = 2) -> None:
    for i in range(w):
        g.line(x0 + i, y0, x1 + i, y1, c)


def sword():
    g = g16(); blade(g, 6, 9, 13, 2); g.line(3, 9, 7, 13, "c"); g.line(4, 9, 8, 13, "c"); g.line(2, 13, 4, 11, "p"); g.set(1, 14, "a")
    return fin(g)


def dagger():
    g = g16(); blade(g, 7, 8, 12, 3); g.line(5, 8, 8, 11, "c"); g.line(3, 13, 6, 10, "p")
    return fin(g)


def knife():
    g = g16(); g.poly([(6, 9), (13, 3), (14, 5), (8, 11)], "m"); g.line(2, 14, 6, 10, "p"); g.line(3, 14, 7, 10, "p")
    return fin(g)


def axe():
    g = g16(); g.line(3, 14, 11, 4, "p"); g.line(4, 14, 12, 4, "p"); g.poly([(9, 2), (14, 4), (13, 9), (10, 6)], "m"); g.set(11, 4, "c")
    return fin(g)


def mace():
    g = g16(); g.line(3, 13, 9, 7, "p"); g.line(4, 13, 10, 7, "p"); g.ellipse(11, 5, 3.2, 3.2, "m")
    for x, y in [(11, 1), (15, 5), (11, 9), (7, 5)]:
        g.set(x, y, "m")
    g.set(11, 5, "c")
    return fin(g)


def spear():
    g = g16(); g.line(1, 15, 11, 5, "p"); g.poly([(10, 4), (14, 1), (12, 6)], "m"); g.set(10, 6, "c")
    return fin(g)


def bow():
    g = g16(); g.line(4, 2, 4, 13, "o")
    for y in range(1, 15):
        g.set(int(10 - abs(y - 7.5) ** 1.3 / 2.6), y, "p")
    g.set(5, 7, "c")
    return fin(g)


def staff():
    g = g16(); g.line(3, 14, 10, 5, "p"); g.line(4, 14, 11, 5, "p"); g.ellipse(12, 3.5, 2.6, 2.6, "c"); g.set(11, 3, "w")
    return fin(g)


def wand():
    g = g16(); g.line(3, 13, 11, 5, "p"); g.set(12, 4, "c").set(13, 3, "w").set(14, 4, "c").set(12, 2, "c")
    return fin(g)


def revolver():
    g = g16(); g.rect(4, 5, 14, 7, "m"); g.rect(6, 4, 9, 9, "M"); g.poly([(4, 7), (7, 7), (6, 13), (3, 13)], "p"); g.set(8, 9, "o"); g.set(13, 4, "m")
    return fin(g, "pm")


def rifle():
    g = g16(); g.line(1, 11, 14, 4, "m"); g.line(1, 12, 14, 5, "m"); g.poly([(1, 11), (5, 9), (6, 12), (2, 14)], "p"); g.set(8, 9, "c")
    return fin(g, "pm")


def wrench():
    g = g16(); blade(g, 3, 13, 10, 6); g.ellipse(11.5, 4.5, 3, 3, "m"); g.rect(12, 3, 13, 4, T); g.set(4, 12, "c")
    return fin(g)


def crowbar():
    g = g16(); blade(g, 3, 13, 11, 3, "c"); g.line(11, 3, 13, 4, "c"); g.line(2, 13, 3, 15, "c")
    return fin(g)


def shield():
    g = g16(); g.poly([(3, 2), (13, 2), (13, 8), (8, 14), (3, 8)], "c"); g.vline(8, 3, 12, "a"); g.hline(4, 12, 6, "a")
    return fin(g, "c")


def helmet():
    g = g16(); g.ellipse(8, 8, 5.5, 5.5, "m"); g.clear(lambda x, y: y > 11); g.rect(3, 10, 13, 11, "c"); g.rect(9, 7, 12, 8, "k")
    return fin(g)


def armor():
    g = g16(); g.poly([(4, 3), (7, 4), (9, 4), (12, 3), (14, 7), (12, 8), (12, 14), (4, 14), (4, 8), (2, 7)], "c"); g.vline(8, 5, 13, "C"); g.hline(4, 12, 10, "a")
    return fin(g, "c")


def coat():
    g = g16(); g.poly([(5, 2), (11, 2), (14, 6), (13, 14), (3, 14), (2, 6)], "c"); g.poly([(6, 2), (8, 7), (10, 2)], "C"); g.vline(8, 7, 14, "C"); g.set(9, 9, "a").set(9, 12, "a")
    return fin(g, "c")


def robe():
    g = g16(); g.poly([(6, 1), (10, 1), (12, 5), (14, 15), (2, 15), (4, 5)], "c"); g.vline(8, 2, 15, "a"); g.hline(3, 13, 14, "a")
    return fin(g, "c")


def boots():
    g = g16(); g.rect(3, 4, 6, 12, "c"); g.rect(3, 12, 8, 14, "c"); g.rect(9, 3, 12, 11, "c"); g.rect(9, 11, 14, 13, "c"); g.hline(3, 6, 4, "a").hline(9, 12, 3, "a")
    return fin(g, "c")


def gloves():
    g = g16(); g.rect(4, 6, 11, 13, "c")
    for x in (4, 6, 8, 10):
        g.rect(x, 2, x + 1, 6, "c")
    g.rect(12, 7, 13, 10, "c"); g.hline(4, 11, 12, "a")
    return fin(g, "c")


def hat():
    g = g16(); g.ellipse(8, 11, 7, 2.2, "c"); g.rect(4, 4, 11, 10, "c"); g.hline(4, 11, 9, "a")
    return fin(g, "c")


def ring():
    g = g16(); g.ellipse(8, 10, 4.5, 4, "a"); g.ellipse(8, 10, 2.5, 2.2, T); g.ellipse(8, 4.5, 2.2, 2.2, "c"); g.set(7, 4, "w")
    return fin(g, "a")


def amulet():
    g = g16(); g.line(3, 1, 8, 8, "a"); g.line(13, 1, 8, 8, "a"); g.poly([(8, 7), (11, 10.5), (8, 14), (5, 10.5)], "c"); g.set(7, 9, "w")
    return fin(g, "c")


def badge():
    g = g16(); g.poly([(8, 1), (10, 6), (15, 6), (11, 9), (13, 14), (8, 11), (3, 14), (5, 9), (1, 6), (6, 6)], "a"); g.ellipse(8, 8, 1.6, 1.6, "c")
    return fin(g, "a")


def potion():
    g = g16(); g.ellipse(8, 10, 5, 4.5, "c"); g.rect(6, 2, 9, 6, "w"); g.rect(6, 1, 9, 2, "p"); g.set(6, 8, "w").set(5, 9, "w")
    return fin(g, "c")


def flask():
    g = g16(); g.poly([(6, 2), (10, 2), (10, 6), (13, 13), (3, 13), (6, 6)], "w"); g.poly([(4, 10), (12, 10), (13, 13), (3, 13)], "c"); g.rect(6, 1, 9, 2, "p")
    return fin(g, "c")


def pouch():
    g = g16(); g.ellipse(8, 10, 5.5, 4.5, "p"); g.poly([(6, 6), (10, 6), (11, 3), (5, 3)], "p"); g.hline(6, 10, 6, "c")
    return fin(g, "p")


def herb():
    g = g16(); g.line(8, 15, 8, 5, "v")
    for y, s in [(5, -1), (8, 1), (11, -1)]:
        g.ellipse(8 + 3 * s, y, 2.6, 1.4, "v")
    g.set(8, 3, "c")
    return fin(g, "v")


def bread():
    g = g16(); g.ellipse(8, 9, 6.5, 4, "p"); g.line(5, 7, 6, 9, "P").line(8, 6, 9, 9, "P").line(11, 7, 12, 9, "P")
    return fin(g, "p")


def apple():
    g = g16(); g.ellipse(8, 9.5, 5, 5, "r"); g.vline(8, 2, 5, "p"); g.ellipse(10.5, 3.5, 2, 1, "v"); g.set(6, 7, "w")
    return fin(g, "r")


def fish():
    g = g16(); g.ellipse(7, 8, 5.5, 3, "c"); g.poly([(11, 8), (15, 4), (15, 12)], "c"); g.set(4, 7, "k")
    return fin(g, "c")


def key():
    g = g16(); g.ellipse(4.5, 5.5, 3, 3, "a"); g.ellipse(4.5, 5.5, 1.2, 1.2, T); blade(g, 6, 7, 13, 14, "a", 2); g.set(11, 14, "a").set(10, 13, "a").set(13, 11, "a")
    return fin(g, "a")


def key_ornate():
    g = g16(); g.ellipse(4.5, 5.5, 3.4, 3.4, "c"); g.ellipse(4.5, 5.5, 1.4, 1.4, "a"); blade(g, 6, 7, 13, 14, "a", 2); g.set(11, 14, "c").set(13, 11, "c")
    return fin(g, "ac")


def letter():
    g = g16(); g.rect(1, 4, 14, 12, "w"); g.line(1, 4, 7, 9, "W").line(14, 4, 8, 9, "W"); g.ellipse(7.5, 9, 1.6, 1.6, "c")
    return fin(g, "")


def book():
    g = g16(); g.rect(3, 2, 13, 14, "c"); g.rect(4, 12, 13, 13, "w"); g.vline(3, 2, 14, "C"); g.rect(6, 5, 11, 7, "a")
    return fin(g, "")


def scroll():
    g = g16(); g.rect(4, 3, 12, 13, "w"); g.ellipse(4, 8, 1.6, 5.5, "W"); g.ellipse(12, 8, 1.6, 5.5, "W")
    for y in (5, 7, 9, 11):
        g.hline(6, 10, y, "k")
    g.set(8, 13, "c")
    return fin(g, "")


def map_():
    g = g16(); g.poly([(1, 3), (5, 2), (10, 4), (15, 3), (15, 13), (10, 14), (5, 12), (1, 13)], "w"); g.vline(5, 2, 12, "W").vline(10, 4, 14, "W")
    g.line(3, 10, 7, 6, "c").line(7, 6, 12, 9, "c"); g.set(12, 8, "r").set(13, 9, "r")
    return fin(g, "")


def coin():
    g = g16(); g.ellipse(8, 8, 6, 6, "a"); g.ellipse(8, 8, 4, 4, "A"); g.rect(7, 5, 8, 10, "a")
    return fin(g, "")


def gem():
    g = g16(); g.poly([(4, 5), (12, 5), (14, 8), (8, 14), (2, 8)], "c"); g.hline(2, 14, 8, "C"); g.line(4, 5, 8, 14, "C").line(12, 5, 8, 14, "C"); g.set(6, 6, "w")
    return fin(g, "")


def crystal():
    g = g16(); g.poly([(6, 14), (5, 6), (8, 1), (11, 6), (10, 14)], "c"); g.vline(8, 2, 14, "C"); g.set(7, 4, "w")
    return fin(g, "")


def lantern():
    g = g16(); g.rect(5, 4, 11, 13, "m"); g.rect(6, 6, 10, 12, "c"); g.ellipse(8, 9, 1.5, 2, "w"); g.hline(4, 12, 4, "m"); g.ellipse(8, 2, 2, 1.5, "m"); g.ellipse(8, 2, 0.8, 0.6, T)
    return fin(g, "")


def candle():
    g = g16(); g.rect(6, 6, 9, 14, "w"); g.ellipse(7.5, 14, 5, 1.5, "m"); g.poly([(6.5, 6), (7.5, 1), (8.5, 6)], "c"); g.set(7, 4, "w")
    return fin(g, "")


def rope():
    g = g16(); g.ellipse(8, 8, 6, 5, "p"); g.ellipse(8, 8, 3.6, 2.8, T); g.ellipse(8, 8, 2, 1.4, "p"); g.line(12, 11, 14, 15, "p")
    for x, y in g.cells():
        if g.get(x, y) == "p" and (x + y) % 3 == 0:
            g.set(x, y, "P")
    return fin(g, "")


def lockpick():
    g = g16(); g.line(2, 13, 12, 3, "m"); g.line(12, 3, 14, 3, "m"); g.line(4, 14, 13, 5, "m"); g.rect(1, 12, 3, 14, "c")
    return fin(g, "")


def bandage():
    g = g16(); g.poly([(2, 10), (10, 2), (14, 6), (6, 14)], "w"); g.poly([(6, 6), (8, 4), (12, 8), (10, 10)], "W"); g.rect(7, 7, 8, 8, "r")
    return fin(g, "")


def pills():
    g = g16(); g.rect(3, 6, 13, 14, "w"); g.rect(3, 3, 13, 5, "c"); g.rect(5, 8, 11, 11, "W"); g.set(8, 9, "r")
    return fin(g, "c")


def camera():
    g = g16(); g.rect(1, 5, 14, 13, "k"); g.rect(4, 3, 8, 5, "k"); g.ellipse(8, 9, 3.4, 3.4, "m"); g.ellipse(8, 9, 1.8, 1.8, "c"); g.set(12, 6, "w")
    return fin(g, "")


def notebook():
    g = g16(); g.rect(3, 2, 13, 14, "c"); g.rect(5, 2, 13, 14, "w")
    for y in (5, 7, 9, 11):
        g.hline(6, 12, y, "W")
    for y in range(3, 14, 2):
        g.set(4, y, "m")
    return fin(g, "")


def photo():
    g = g16(); g.rect(2, 2, 13, 13, "w"); g.rect(4, 4, 11, 10, "c"); g.ellipse(7.5, 7, 1.6, 1.6, "C"); g.rect(5, 9, 10, 10, "C")
    return fin(g, "")


def skull():
    g = g16(); g.ellipse(8, 7, 5.5, 5, "w"); g.rect(5, 10, 11, 13, "w")
    g.rect(5, 6, 6, 8, "k").rect(10, 6, 11, 8, "k").set(8, 9, "k")
    for x in (6, 8, 10):
        g.vline(x, 12, 13, "W")
    return fin(g, "")


def feather():
    g = g16(); g.poly([(3, 14), (6, 7), (12, 1), (13, 3), (9, 10)], "c"); g.line(2, 15, 12, 2, "w")
    return fin(g, "c")


def bomb():
    g = g16(); g.ellipse(7, 10, 5, 5, "k"); g.line(10, 5, 13, 2, "p"); g.set(14, 1, "c").set(13, 1, "a"); g.set(5, 8, "m")
    return fin(g, "")


ICONS = [
    ("sword", "меч", sword), ("dagger", "кинжал", dagger), ("knife", "нож", knife), ("axe", "топор", axe),
    ("mace", "булава", mace), ("spear", "копьё", spear), ("bow", "лук", bow), ("staff", "посох", staff),
    ("wand", "волшебная палочка", wand), ("revolver", "револьвер", revolver), ("rifle", "ружьё или винтовка", rifle),
    ("wrench", "гаечный ключ", wrench), ("crowbar", "монтировка, лом", crowbar), ("shield", "щит", shield),
    ("helmet", "шлем", helmet), ("armor", "доспех, кираса, бронежилет", armor), ("coat", "плащ, пальто, куртка", coat),
    ("robe", "мантия, ряса", robe), ("boots", "сапоги, ботинки", boots), ("gloves", "перчатки", gloves),
    ("hat", "шляпа, кепка", hat), ("ring", "кольцо", ring), ("amulet", "амулет, кулон", amulet),
    ("badge", "значок, жетон, орден", badge), ("potion", "зелье, настойка", potion), ("flask", "колба, бутыль, реактив", flask),
    ("pouch", "мешочек, кисет", pouch), ("herb", "трава, растение", herb), ("bread", "хлеб, еда", bread),
    ("apple", "фрукт, яблоко", apple), ("fish", "рыба", fish), ("key", "ключ", key), ("key_ornate", "старинный или волшебный ключ", key_ornate),
    ("letter", "письмо, конверт", letter), ("book", "книга, журнал", book), ("scroll", "свиток", scroll),
    ("map", "карта", map_), ("coin", "монета", coin), ("gem", "драгоценный камень", gem), ("crystal", "кристалл", crystal),
    ("lantern", "фонарь", lantern), ("candle", "свеча", candle), ("rope", "верёвка", rope), ("lockpick", "отмычка", lockpick),
    ("bandage", "бинт, аптечка", bandage), ("pills", "таблетки, лекарство", pills), ("camera", "фотоаппарат", camera),
    ("notebook", "блокнот", notebook), ("photo", "фотография", photo), ("skull", "череп", skull),
    ("feather", "перо", feather), ("bomb", "бомба, граната", bomb),
]


def build() -> dict[str, list[dict]]:
    out = []
    for id, description, fn in ICONS:
        g = fn()
        out.append({"id": id, "slot": "icon", "description": description, "w": 16, "h": 16, "anchor": [0, 0],
                    "pixels": ["".join(r) for r in g.px]})
    return {"icon": out}
