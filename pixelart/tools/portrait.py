"""Детали портрета 48×48 (SPEC §5.7.2).

Все детали рисуются на полном холсте и обрезаются с anchor относительно
REF = (24, 24): рендер ставит anchor каждой детали в эту точку, поэтому
слои не съезжают. Ось симметрии лица — x = 24.0 (между пикселями 23 и 24).

Фиксированная разметка лица: глаза — строки 20–22 (нижняя 22), внутренние
края x=20 и x=27; брови — нижняя строка 18; рот — строка 28.
"""

from __future__ import annotations

import math

from px import T, Grid, from_rows

W = H = 48
CX = 24.0
REF = (24, 24)
EMOTIONS = ["neutral", "angry", "sad", "happy", "scared", "surprised"]

EYE_BOTTOM = 22
EYE_INNER_L, EYE_INNER_R = 20, 27
BROW_BOTTOM = 18
MOUTH_Y = 28


def grid() -> Grid:
    return Grid(W, H)


def part(id: str, slot: str, description: str, g: Grid, **extra) -> dict:
    return {"id": id, "slot": slot, "description": description, **g.sprite(REF), **extra}


def interp(points: list[tuple[float, float]], y: float) -> float | None:
    if y < points[0][0] or y > points[-1][0]:
        return None
    for (y0, v0), (y1, v1) in zip(points, points[1:]):
        if y0 <= y <= y1:
            return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
    return points[-1][1]


def profile_fill(g: Grid, points: list[tuple[float, float]], c: str, over: str | None = None) -> Grid:
    def inside(x: float, y: float) -> bool:
        hw = interp(points, y)
        return hw is not None and abs(x - CX) <= hw
    return g.fill(inside, c, over)


# --- головы ------------------------------------------------------------------

HEADS = {
    "oval": ("овальное лицо, универсальное",
             [(9, 5), (10, 7.5), (11, 8.8), (13, 9.8), (15, 10), (24, 10), (27, 9.2), (29, 8), (31, 6), (32, 4.5), (33, 3)]),
    "round": ("круглое мягкое лицо, полные щёки",
              [(9, 6), (10, 8.5), (11, 10), (13, 10.8), (15, 11), (25, 11), (27, 10.3), (29, 9), (30.5, 7.5), (31.5, 5.5), (32.2, 4)]),
    "square": ("квадратное лицо, тяжёлая челюсть",
               [(9, 7), (10, 9.3), (11, 10.3), (12, 10.8), (14, 11), (28, 11), (30, 10.5), (31.5, 9.5), (32.5, 8), (33.2, 6)]),
    "thin": ("худое вытянутое лицо, острый подбородок",
             [(8, 4.5), (9, 7), (10, 8.2), (12, 9), (23, 9), (26, 8.3), (29, 6.8), (31, 5), (33, 3.5), (34.2, 2)]),
    "heart": ("лицо сердечком: широкий лоб, узкий подбородок",
              [(9, 6), (10, 9), (11, 10.5), (13, 11), (18, 11), (22, 10.3), (26, 8.6), (29, 6.4), (31, 4.5), (33, 2.5)]),
    "old": ("пожилое лицо с морщинами",
            [(9, 5), (10, 7.5), (11, 8.8), (13, 9.8), (15, 10), (25, 10), (28, 9.4), (30, 8.2), (31.5, 6.5), (32.5, 4.8), (33.3, 3.2)]),
}


def make_head(name: str) -> dict:
    description, points = HEADS[name]
    g = grid()
    chin = points[-1][0]
    g.rect(20, int(chin) - 4, 27, 39, "s")  # шея
    ear_hw = interp(points, 21.5)
    for side in (-1, 1):
        g.ellipse(CX + side * (ear_hw + 0.6), 22, 1.7, 2.6, "s")
    profile_fill(g, points, "s")
    g.outline()
    g.shade("s", "right", 2)
    # тень под подбородком на шее
    for x in range(20, 28):
        for y in range(int(chin) + 1, int(chin) + 3):
            if g.get(x, y) in "sS" and interp(points, y + 0.5) is None:
                g.set(x, y, "S")
    # ухо: внутренняя тень
    for side in (-1, 1):
        g.set(int(CX + side * (ear_hw + 0.6) - (0.5 if side < 0 else -0.5)) - (0 if side < 0 else 1), 22, "S")
    # нос
    for x, y in [(24, 24), (24, 25), (23, 26), (24, 26)]:
        g.set(x, y, "S")
    if name == "old":
        for x, y in [(17, 23), (18, 23), (19, 23), (28, 23), (29, 23), (30, 23),  # мешки под глазами
                     (20, 26), (20, 27), (21, 28), (27, 26), (27, 27), (26, 28),  # носогубные
                     (15, 21), (32, 21), (19, 13), (20, 13), (21, 13), (26, 13), (27, 13), (28, 13)]:
            if g.get(x, y) == "s":
                g.set(x, y, "S")
    return part(name, "head", description, g)


# --- глаза ---------------------------------------------------------------------

# Левый глаз (внешний край слева, внутренний справа). Правый — зеркало.
EYES = {
    "round": ("круглые открытые глаза", ["oooo", "wkkw", "weew"]),
    "narrow": ("узкие спокойные глаза", ["ooooo", "wwkkw"]),
    "sharp": ("острые миндалевидные глаза, внимательный взгляд", ["oooo.", "owkkw"]),
    "big": ("большие выразительные глаза", ["oooo", "wwkw", "wkkw", "weew"]),
    "sleepy": ("тяжёлые веки, усталый или скучающий взгляд", ["SSSS", "oooo", "wkkw"]),
    "small": ("маленькие глаза-точки", ["oo.", "kk."]),
}


def _eye_body(rows: list[str]) -> list[str]:
    """Строки под линией ресниц (первая строка, содержащая 'o')."""
    for i, row in enumerate(rows):
        if "o" in row:
            return rows[i + 1:] or [row]
    return rows


def eye_emotion(rows: list[str], emotion: str) -> list[str]:
    w = len(rows[0])
    rows = [list(r) for r in rows]
    lash = next(i for i, r in enumerate(rows) if "o" in r)
    if emotion == "neutral":
        pass
    elif emotion in ("angry", "sad"):
        outer, inner = (0, w - 1) if emotion == "angry" else (w - 1, 0)
        if lash + 1 < len(rows):
            rows[lash][outer] = T
            rows[lash + 1][inner] = "o"
            # тяжёлое веко: ещё пиксель контура внутрь
            step = -1 if emotion == "angry" else 1
            if 0 <= inner + step < w and rows[lash + 1][inner + step] == "w":
                rows[lash + 1][inner + step] = "o" if emotion == "angry" else rows[lash + 1][inner + step]
    elif emotion == "happy":
        if w <= 3 and sum(c != T for c in rows[-1]) <= 2:
            arc = ["".join("o" if c != T else T for c in rows[-1])]
        else:
            arc = [T + "o" * (w - 2) + T, "o" + T * (w - 2) + "o"]
        return [T * w] * (len(rows) - len(arc)) + arc
    elif emotion in ("surprised", "scared"):
        body = ["".join(r) for r in rows[lash + 1:]] or ["".join(rows[-1])]
        body = [r.replace("S", "w") for r in body]
        if emotion == "scared":
            body = [r.replace("e", "w") for r in body]
            # зрачок сужается до одного пикселя
            body = [r.replace("kk", "wk", 1) if i == 0 else r.replace("k", "w") for i, r in enumerate(body)]
        top = "o" * w if "o" * w != "".join(rows[lash]).replace(T, "o") else "".join(rows[lash])
        return ["o" * w, "w" * w if w > 2 else "w" * w] + body
    return ["".join(r) for r in rows]


def make_eyes(name: str) -> dict:
    description, rows = EYES[name]
    variants = {}
    for emotion in EMOTIONS:
        left = eye_emotion(rows, emotion)
        g = grid()
        h, w = len(left), len(left[0])
        y0 = EYE_BOTTOM - h + 1
        g.draw(left, EYE_INNER_L - w + 1, y0)
        g.draw([r[::-1] for r in left], EYE_INNER_R, y0)
        variants[emotion] = g.sprite(REF)
    return {"id": name, "slot": "eyes", "description": description, **variants["neutral"], "variants": variants}


# --- брови ---------------------------------------------------------------------

BROWS = {
    "straight": ("прямые брови", ["HHHHH"]),
    "thick": ("густые широкие брови", ["HHHHH", "HHHHH"]),
    "thin": ("тонкие аккуратные брови", ["HHHH"]),
    "arched": ("высокие дугообразные брови", [".HHH.", "H...H"]),
    "bushy": ("косматые нависающие брови", ["HhHhH.", "HHHHHH"]),
}


def brow_offsets(w: int, emotion: str) -> list[int]:
    t = [i / (w - 1) for i in range(w)]  # 0 — внешний край, 1 — внутренний
    return {
        "neutral": [0] * w,
        "angry": [round(2 * v) for v in t],
        "sad": [-round(2 * v) for v in t],
        "surprised": [-2] * w,
        "scared": [-1 - round(v) for v in t],
        "happy": [-1] * w,
    }[emotion]


def make_brows(name: str) -> dict:
    description, rows = BROWS[name]
    variants = {}
    w, h = len(rows[0]), len(rows)
    for emotion in EMOTIONS:
        offsets = brow_offsets(w, emotion)
        g = grid()
        x0 = EYE_INNER_L - w + 1
        for i in range(w):
            for j in range(h):
                c = rows[j][i]
                if c == T:
                    continue
                y = BROW_BOTTOM - h + 1 + j + offsets[i]
                g.set(x0 + i, y, c)
                g.set(EYE_INNER_R + (w - 1 - i), y, c)
        variants[emotion] = g.sprite(REF)
    return {"id": name, "slot": "brows", "description": description, **variants["neutral"], "variants": variants}


# --- рты -------------------------------------------------------------------------

MOUTHS = {
    "thin": ("тонкие губы, сдержанный рот", 4),
    "full": ("полные губы", 4),
    "small": ("маленький аккуратный рот", 2),
    "wide": ("широкий рот", 6),
    "smirk": ("кривая ухмылка, ирония или высокомерие", 4),
    "stern": ("строгий рот с опущенными уголками", 4),
}


def mouth_grid(name: str, emotion: str) -> Grid:
    g = grid()
    width = MOUTHS[name][1]
    x0, x1 = 24 - width // 2, 24 + width // 2 - 1
    y = MOUTH_Y
    if emotion == "neutral":
        if name == "smirk":
            g.hline(x0, x1, y, "o").set(x1 + 1, y - 1, "o")
        elif name == "stern":
            g.hline(x0, x1, y, "o").set(x0 - 1, y + 1, "o").set(x1 + 1, y + 1, "o")
        else:
            g.hline(x0, x1, y, "o")
        if name == "full":
            g.hline(x0, x1, y + 1, "r")
    elif emotion == "happy":
        if name in ("full", "wide"):
            g.set(x0 - 1, y - 1, "o").set(x1 + 1, y - 1, "o")
            g.hline(x0, x1, y, "o")
            g.set(x0, y + 1, "o").hline(x0 + 1, x1 - 1, y + 1, "w").set(x1, y + 1, "o")
            g.hline(x0 + 1, x1 - 1, y + 2, "o")
        else:
            g.set(x0 - 1, y - 1, "o").set(x1 + 1, y - 1, "o").hline(x0, x1, y, "o")
            if name == "smirk":
                g.set(x1 + 1, y - 2, "o")
    elif emotion == "sad":
        g.hline(x0, x1, y, "o").set(x0 - 1, y + 1, "o").set(x1 + 1, y + 1, "o")
        if name == "full":
            g.hline(x0, x1, y - 1, "r")
    elif emotion == "angry":
        x0, x1 = min(x0, 22), max(x1, 25)
        g.hline(x0 - 1, x1 + 1, y - 1, "o")
        g.set(x0 - 1, y, "o").hline(x0, x1, y, "w").set(x1 + 1, y, "o")
        g.hline(x0 - 1, x1 + 1, y + 1, "o")
        for x in range(x0 + 1, x1, 2):
            g.set(x, y, "W")
    elif emotion == "scared":
        x0, x1 = max(x0, 22), min(x1, 25)
        g.hline(x0, x1, y - 1, "o")
        g.set(x0 - 1, y, "o").hline(x0, x1, y, "k").set(x1 + 1, y, "o")
        g.hline(x0, x1, y + 1, "o")
        g.set(x0 - 1, y + 1, T).set(x1, y + 1, T).set(x1 + 1, y + 1, "o")  # дрожащий изгиб
    elif emotion == "surprised":
        rows = [".oo.", "okko", "okko", ".oo."] if name != "small" else ["oo", "kk", "oo"]
        g.draw(rows, 24 - len(rows[0]) // 2, y - 1)
    return g


def make_mouth(name: str) -> dict:
    variants = {e: mouth_grid(name, e).sprite(REF) for e in EMOTIONS}
    return {"id": name, "slot": "mouth", "description": MOUTHS[name][0], **variants["neutral"], "variants": variants}


# --- растительность на лице ---------------------------------------------------

def make_facial_hair(name: str) -> dict:
    g = grid()
    mouth_hole = lambda x, y: ((x - CX) / 3.6) ** 2 + ((y - 28.6) / 1.7) ** 2 <= 1
    if name == "stubble":
        g.fill(lambda x, y: ((x - CX) / 11) ** 2 + ((y - 24) / 10) ** 2 <= 1 and y >= 25.5 and not mouth_hole(x, y), "H")
        for x, y in g.cells():
            if g.get(x, y) == "H" and (x * 5 + y * 3) % 7 not in (0, 3):
                g.set(x, y, T)
        return part(name, "facial_hair", "щетина", g, clip="head")
    if name == "mustache":
        g.rect(20, 26, 27, 26, "h").rect(19, 27, 21, 27, "h").rect(26, 27, 28, 27, "h")
        g.set(19, 28, "h").set(28, 28, "h")
        g.outline().shade("h", "down", 1)
        return part(name, "facial_hair", "густые усы", g)
    if name == "full_beard":
        g.fill(lambda x, y: ((x - CX) / 11.8) ** 2 + ((y - 25.5) / 11.5) ** 2 <= 1
               and (y >= 27 or (abs(x - CX) >= 9 and y >= 21)), "h")
        g.clear(mouth_hole)
        g.outline().shade("h", "right", 2).shade("h", "down", 1)
        return part(name, "facial_hair", "окладистая борода с усами", g)
    if name == "goatee":
        g.fill(lambda x, y: ((x - CX) / 3.6) ** 2 + ((y - 32) / 3.2) ** 2 <= 1 and y >= 30, "h")
        g.rect(21, 26, 26, 26, "h").rect(20, 27, 20, 29, "h").rect(27, 27, 27, 29, "h")
        g.outline().shade("h", "right", 1)
        return part(name, "facial_hair", "эспаньолка: усы и бородка", g)
    raise KeyError(name)


FACIAL_HAIR = ["stubble", "mustache", "full_beard", "goatee"]


# --- причёски ------------------------------------------------------------------

SKULL = (CX, 18.5, 12.2, 11.0)


def in_skull(x: float, y: float, grow: float = 0.0) -> bool:
    cx, cy, rx, ry = SKULL
    return ((x - cx) / (rx + grow)) ** 2 + ((y - cy) / (ry + grow)) ** 2 <= 1


def cap(g: Grid, fringe, c: str = "h") -> Grid:
    return g.fill(lambda x, y: in_skull(x, y) and y < fringe(x), c)


def side(x: float, dist: float = 9.5) -> bool:
    return abs(x - CX) > dist


def finish(g: Grid, c: str = "h") -> Grid:
    return g.outline().shade(c, "right", 2)


def make_hair(name: str) -> dict:
    front, back = grid(), grid()
    c = "h"
    if name == "short_messy":
        description = "короткие взъерошенные волосы"
        back.fill(lambda x, y: in_skull(x, y) and y < 23, c)
        cap(front, lambda x: 20 if side(x) else 13.5 + 2 * ((int(x) // 2) % 2))
    elif name == "short_neat":
        description = "короткая аккуратная стрижка с пробором"
        back.fill(lambda x, y: in_skull(x, y) and y < 22, c)
        cap(front, lambda x: 19 if side(x) else (12.5 if x > 18 else 13.5))
        front.vline(18, 8, 12, "H")
    elif name == "crew_cut":
        description = "очень короткая стрижка «ёжик», почти под ноль"
        front.fill(lambda x, y: in_skull(x, y, -0.9) and y < (16 if side(x) else 12.5), c)
        front.dither("h", "H", 1)
    elif name == "side_part":
        description = "зачёс набок с косой чёлкой"
        back.fill(lambda x, y: in_skull(x, y) and y < 23, c)
        cap(front, lambda x: (19 if x < CX else 21) if side(x) else min(16, 11 + 0.42 * (x - 12)))
        front.vline(16, 7, 10, "H")
    elif name == "long_straight":
        description = "длинные прямые волосы ниже плеч"
        back.fill(lambda x, y: in_skull(x, y) or (11.5 <= x <= 36.5 and 17 <= y <= 42 - abs(x - CX) * 0.15), c)
        cap(front, lambda x: 12.5)
        front.fill(lambda x, y: (11.5 <= x <= 15.5 or 32.5 <= x <= 36.5) and 12 <= y <= 43 - abs(x - CX) * 0.2, c)
        front.vline(23, 7, 11, "H")
    elif name == "long_braid":
        description = "длинная коса, перекинутая через плечо"
        # волосы за шеей заполняют щель между челюстью, шеей и косой
        back.fill(lambda x, y: in_skull(x, y) and y < 25 or (25 <= x <= 35 and 24 <= y <= 37), c)
        cap(front, lambda x: (20 if x < CX else 23) if side(x) else min(15, 12 + 0.2 * (x - 12)))
        for i, y in enumerate(range(25, 44, 4)):
            front.ellipse(33.5 - i * 0.4, y + 1.5, 2.6, 2.3, "h")
        front.outline()
        for i, y in enumerate(range(25, 44, 4)):
            front.hline(32 - int(i * 0.4), 35 - int(i * 0.4), y + 3, "H")
        front.rect(31, 44, 34, 45, "a").outline()
        front.shade("h", "right", 1)
        return {**part(name, "hair", description, front), "back": finish(back).sprite(REF)}
    elif name == "ponytail":
        description = "гладко зачёсанные волосы, хвост на затылке"
        back.fill(lambda x, y: in_skull(x, y) and y < 24, c)
        for i, y in enumerate(range(13, 31, 3)):
            back.ellipse(36 + i * 0.5, y + 1, 2.8 - i * 0.2, 2.4, c)
        cap(front, lambda x: 18 if side(x) else 11.5)
        front.rect(34, 13, 35, 15, "a")
    elif name == "bun":
        description = "волосы собраны в пучок на макушке"
        back.fill(lambda x, y: in_skull(x, y) and y < 23, c)
        back.ellipse(CX, 5.5, 4.6, 4.0, c)
        cap(front, lambda x: 18 if side(x) else 11.5)
        front.rect(21, 8, 26, 8, "a")
    elif name == "curly":
        description = "пышные кудрявые волосы"
        back.fill(lambda x, y: in_skull(x, y, 0.8) and y < 28, c)
        for a in range(0, 360, 30):
            px_, py_ = CX + 12.8 * math.cos(math.radians(a)), 18 + 11.5 * math.sin(math.radians(a))
            if py_ < 28:
                back.ellipse(px_, py_, 3.4, 3.2, c)
        front.fill(lambda x, y: in_skull(x, y) and y < 11, c)
        for x in range(13, 36, 3):
            front.ellipse(x + 0.5, 12, 2.6, 2.4, c)
        for y in (15, 19):
            front.ellipse(13, y, 2.4, 2.6, c).ellipse(35, y, 2.4, 2.6, c)
        front.dither("h", "H", 0)
        front.replace("H", "h")
        for x, y in front.cells():
            if front.get(x, y) == "h" and (x * 3 + y * 5) % 7 == 0:
                front.set(x, y, "H")
    elif name == "afro":
        description = "объёмная причёска афро"
        back.ellipse(CX, 15, 16.5, 14.5, c)
        for a in range(0, 360, 24):
            back.ellipse(CX + 16 * math.cos(math.radians(a)), 15 + 14 * math.sin(math.radians(a)), 2.4, 2.4, c)
        back.clear(lambda x, y: y > 30)
        front.fill(lambda x, y: in_skull(x, y) and y < 11.5, c)
        for x in range(13, 36, 3):
            front.ellipse(x + 0.5, 11.5, 2.2, 2.0, c)
    elif name == "mohawk":
        description = "ирокез, выбритые виски"
        pts = [(20.5, 13), (20.5, 6)]
        for i, x in enumerate(range(21, 28)):
            pts.append((x, 0.5 if i % 2 == 0 else 3.5))
        pts += [(27.5, 6), (27.5, 13)]
        front.poly(pts, c)
        front.fill(lambda x, y: abs(x - CX) < 3.5 and in_skull(x, y) and y < 13, c)
    elif name == "bob":
        description = "каре до подбородка с прямой чёлкой"
        back.fill(lambda x, y: in_skull(x, y) or (11 <= x <= 37 and 17 <= y <= 31.5), c)
        front.fill(lambda x, y: in_skull(x, y) and y < 15.5, c)
        front.fill(lambda x, y: (11 <= x <= 15.2 or 32.8 <= x <= 37) and 12 <= y <= 31.5, c)
        front.hline(13, 34, 15, "H")
    elif name == "balding":
        description = "лысина с венчиком волос по бокам"
        back.fill(lambda x, y: in_skull(x, y) and 15 <= y < 25 and side(x, 7.5), c)
        front.fill(lambda x, y: (11.5 <= x <= 14.6 or 33.4 <= x <= 36.5) and 15 <= y <= 21, c)
    elif name == "hood":
        description = "капюшон (цвета одежды), скрывает волосы"
        c = "c"
        back.fill(lambda x, y: ((x - CX) / 15.2) ** 2 + ((y - 19) / 14.5) ** 2 <= 1 or (9 + (y - 30) * 0.2 <= x <= 39 - (y - 30) * 0.2 and 30 <= y <= 40), c)
        opening = lambda x, y: ((x - CX) / 10.6) ** 2 + ((y - 22) / 12.5) ** 2 <= 1
        front.fill(lambda x, y: ((x - CX) / 15.2) ** 2 + ((y - 19) / 14.5) ** 2 <= 1 and not opening(x, y) and y < 37, c)
        front.fill(lambda x, y: opening(x, y) and not (((x - CX) / 9.6) ** 2 + ((y - 23) / 11.8) ** 2 <= 1) and y < 20, "k")
        front.outline().shade("c", "right", 3)
        back.outline().shade("c", "right", 3)
        return {**part(name, "hair", description, front), "back": back.sprite(REF)}
    else:
        raise KeyError(name)

    finish(front, c)
    result = part(name, "hair", description, front)
    if back.bbox():
        result["back"] = finish(back, c).sprite(REF)
    return result


HAIR = ["short_messy", "short_neat", "crew_cut", "side_part", "long_straight", "long_braid", "ponytail",
        "bun", "curly", "afro", "mohawk", "bob", "balding", "hood"]


# --- наряды -----------------------------------------------------------------------

BODY = [(34.5, 5), (36, 8), (37, 11), (38, 14), (39, 16), (40, 17), (41, 17.6), (48, 18.6)]


def body(c: str = "c") -> Grid:
    g = grid()
    profile_fill(g, BODY, c)
    return g


def v_region(top: float, slope: float, extra: float = 0.0):
    return lambda x, y: y >= top and abs(x - CX) < (y - top) * slope + extra


def make_outfit(name: str) -> dict:
    g = body()
    if name == "detective_coat":
        description = "плащ детектива с поднятым воротником, рубашка и галстук"
        g.fill(v_region(36, 0.5, 2.5), "C")
        g.fill(v_region(36, 0.5), "w")
        g.rect(23, 38, 24, 46, "a").rect(22, 37, 25, 38, "a")
        g.outline()
        collar = grid()
        # задняя часть воротника за шеей: голова рисуется поверх, щели под челюстью закрыты тканью
        collar.poly([(14.5, 30.5), (33.5, 30.5), (34.5, 36), (13.5, 36)], "C")
        collar.poly([(13.5, 33.5), (20.5, 35.5), (20.5, 40.5), (16, 40), (12.5, 37)], "c")
        collar.poly([(34.5, 33.5), (27.5, 35.5), (27.5, 40.5), (32, 40), (35.5, 37)], "c")
        collar.outline()
        collar.shade("c", "right", 1)
        g.stamp(collar)
        for y in (42, 45):
            g.set(17, y, "m").set(30, y, "m")
        g.hline(8, 15, 46, "C").hline(32, 39, 46, "C")
        g.shade("c", "right", 3)
    elif name == "plate_armor":
        description = "латный доспех с наплечниками и гербовой накидкой"
        g.replace("c", "m")
        g.rect(20, 41, 27, 47, "c").vline(20, 41, 47, "a").vline(27, 41, 47, "a")
        g.hline(8, 19, 44, "M").hline(28, 39, 44, "M")
        g.outline()
        pads = grid()
        pads.ellipse(11, 40.5, 6.2, 4.6, "m").ellipse(37, 40.5, 6.2, 4.6, "m")
        pads.outline()
        pads.hline(6, 15, 41, "M").hline(33, 42, 41, "M")
        g.stamp(pads)
        gorget = grid().rect(17, 35, 30, 37, "m")
        gorget.outline()
        g.stamp(gorget)
        g.shade("m", "right", 2).shade("c", "right", 1)
    elif name == "mage_robe":
        description = "мантия мага со стоячим воротником и вышивкой"
        g.fill(v_region(35, 0.5), "C")
        g.fill(lambda x, y: v_region(35, 0.5, 1.6)(x, y) and not v_region(35, 0.5)(x, y), "a")
        g.outline()
        collar = grid()
        collar.rect(15, 31, 18, 38, "a").rect(29, 31, 32, 38, "a")
        collar.outline()
        g.stamp(collar)
        g.draw([".a.", "aAa", ".a."], 12, 42)
        g.draw([".a.", "aAa", ".a."], 33, 42)
        g.shade("c", "right", 3)
    elif name == "business_suit":
        description = "деловой костюм: пиджак, белая рубашка, галстук"
        g.fill(v_region(34, 0.5, 2.0), "C")
        g.fill(v_region(34, 0.5), "w")
        g.rect(23, 38, 24, 46, "a").rect(22, 37, 25, 37, "a")
        g.outline()
        g.rect(30, 42, 32, 42, "w")
        g.shade("c", "right", 3)
    elif name == "work_jacket":
        description = "рабочая куртка на молнии с карманами"
        g.fill(lambda x, y: y <= 37.5 and 3.5 <= abs(x - CX) <= 9, "a", over="c")
        g.vline(24, 38, 47, "m")
        g.outline()
        for x0 in (12, 30):
            g.rect(x0, 43, x0 + 5, 46, "C").hline(x0, x0 + 5, 43, "a")
        g.shade("c", "right", 3)
    elif name == "dress":
        description = "платье с открытыми плечами на бретелях"
        g.fill(lambda x, y: y < 40 + (1.5 if abs(x - CX) < 2 else 0), "s", over="c")
        g.fill(lambda x, y: 40 <= y <= 40.9 + (1.5 if abs(x - CX) < 2 else 0) and g.get(int(x), int(y)) == "c", "a")
        g.rect(15, 36, 16, 40, "a").rect(31, 36, 32, 40, "a")
        g.outline()
        g.shade("s", "right", 2).shade("c", "right", 3)
    elif name == "scifi_armor":
        description = "футуристическая броня со светящимися линиями"
        g.vline(17, 40, 47, "a").vline(30, 40, 47, "a")
        g.hline(8, 16, 43, "C").hline(31, 39, 43, "C")
        g.outline()
        ring = grid().rect(16, 34, 31, 37, "m")
        ring.outline()
        g.stamp(ring)
        g.draw([".a.", "awa", ".a."], 23, 41)
        pads = grid()
        pads.poly([(5, 42), (9, 37.5), (16, 38), (15, 42)], "m").poly([(43, 42), (39, 37.5), (32, 38), (33, 42)], "m")
        pads.outline()
        g.stamp(pads)
        g.shade("c", "right", 3).shade("m", "right", 1)
    elif name == "rags":
        description = "лохмотья: рваная одежда в заплатах"
        g.fill(lambda x, y: y < 39.5 + (2 if x % 4 < 2 else 0) and abs(x - CX) < 8, "s", over="c")
        for x, y in g.cells():
            if g.get(x, y) == "c" and (x * 7 + y * 3) % 9 == 0:
                g.set(x, y, "C")
        # прорехи и бахрома по плечам
        for x0, y0 in [(12, 43), (33, 41), (19, 46)]:
            g.rect(x0, y0, x0 + 1, y0 + 1, "s")
        for x in range(7, 42, 2):
            top = next((y for y in range(48) if g.get(x, y) == "c"), None)
            if top is not None and top < 46:
                g.set(x, top, T)
        g.rect(26, 43, 30, 46, "a")
        g.outline()
        for x, y in [(26, 43), (30, 43), (26, 46), (30, 46)]:
            g.set(x, y, "o")
        g.shade("s", "right", 1).shade("c", "right", 2)
    elif name == "peasant_tunic":
        description = "простая льняная рубаха со шнуровкой"
        g.fill(v_region(36, 0.32), "w")
        g.outline()
        for y in range(38, 45, 2):
            half = (y - 36) * 0.32
            g.set(int(CX - half) - 1, y, "o").set(int(CX + half), y, "o")
        g.shade("c", "right", 3)
    elif name == "noble_coat":
        description = "камзол аристократа с золотой отделкой и жабо"
        g.rect(22, 38, 22, 47, "a").rect(25, 38, 25, 47, "a")
        g.fill(lambda x, y: y <= 37.5 and 4.5 <= abs(x - CX) <= 7.5, "a", over="c")
        g.outline()
        jabot = grid().draw(["wwww", "wWWw", ".ww.", "wWWw", ".ww."], 22, 36)
        g.stamp(jabot)
        for y in (40, 43, 46):
            g.set(20, y, "a").set(27, y, "a")
        g.shade("c", "right", 3)
    elif name == "leather_armor":
        description = "кожаная броня с ремнями и наплечниками"
        g.outline()
        for i in range(-1, 1):
            g.line(13 + i, 37, 34 + i, 47, "a")
        g.draw(["mmm", "m.m", "mmm"], 22, 41)
        pads = grid().ellipse(12, 39, 5.5, 3.2, "C").ellipse(36, 39, 5.5, 3.2, "C")
        pads.outline()
        g.stamp(pads)
        g.shade("c", "right", 2)
    elif name == "military_uniform":
        description = "военный мундир с эполетами и двумя рядами пуговиц"
        g.fill(lambda x, y: y <= 37.5 and abs(x - CX) <= 6, "a", over="c")
        g.outline()
        ep = grid().rect(8, 37, 15, 38, "a").rect(32, 37, 39, 38, "a")
        ep.outline()
        for x in range(8, 16, 2):
            ep.set(x, 39, "a").set(x + 24, 39, "a")
        g.stamp(ep)
        for y in (40, 43, 46):
            g.set(21, y, "m").set(26, y, "m")
        g.set(15, 42, "m").set(15, 43, "a")
        g.shade("c", "right", 3)
    else:
        raise KeyError(name)
    return part(name, "outfit", description, g)


OUTFITS = ["detective_coat", "plate_armor", "mage_robe", "business_suit", "work_jacket", "dress",
           "scifi_armor", "rags", "peasant_tunic", "noble_coat", "leather_armor", "military_uniform"]


# --- аксессуары ---------------------------------------------------------------------

def make_accessory(name: str) -> dict:
    g = grid()
    extra: dict = {}
    if name == "glasses":
        description = "очки в тонкой оправе"
        for x0 in (15, 26):
            g.rect(x0, 19, x0 + 6, 23, "o").rect(x0 + 1, 20, x0 + 5, 22, T)
            g.set(x0 + 1, 20, "w")
        g.hline(22, 25, 20, "o").hline(13, 14, 20, "o").hline(33, 34, 20, "o")
    elif name == "monocle":
        description = "монокль на цепочке"
        g.ellipse(28.5, 21, 3.4, 3.0, "m")
        g.ellipse(28.5, 21, 2.3, 2.0, T)
        g.line(28, 24, 27, 26, "m").vline(27, 26, 38, "m")  # цепочка вдоль шеи, не замыкает фон
    elif name == "eyepatch":
        description = "чёрная повязка на глаз"
        g.ellipse(18.5, 21, 3.4, 2.8, "k")
        g.line(16, 19, 12, 16, "k").line(21, 19, 35, 13, "k")
    elif name == "scar":
        description = "шрам через бровь и щёку"
        g.line(29, 16, 31, 26, "R").line(30, 16, 32, 26, "r")
        for y in (18, 21, 24):
            g.set(28 if y < 21 else 29, y, "o").set(31 if y < 21 else 32, y, "o")
        extra["clip"] = "head"
    elif name == "earring":
        description = "серьги-капли в ушах"
        for x in (13, 34):
            g.set(x, 25, "m").set(x, 26, "a").set(x, 27, "a")
    elif name == "headband":
        description = "повязка на лбу с завязками"
        g.fill(lambda x, y: abs(x - CX) <= 11.5 and 12 + ((x - CX) / 12) ** 2 * 2 <= y <= 14 + ((x - CX) / 12) ** 2 * 2, "a")
        g.rect(34, 13, 36, 17, "a").rect(36, 15, 37, 19, "a")
        g.outline().shade("a", "down", 1)
    elif name == "fedora":
        description = "фетровая шляпа с полями"
        g.ellipse(CX, 11.5, 15.5, 2.2, "a")
        g.fill(lambda x, y: 15 <= x <= 33 and 3.5 <= y <= 11 and not (y < 5 and abs(x - CX) < 3), "a")
        g.fill(lambda x, y: 15 <= x <= 33 and 8.5 <= y <= 10, "k")
        g.outline().shade("a", "right", 2)
    elif name == "wizard_hat":
        description = "остроконечная шляпа волшебника"
        g.poly([(27, 0), (30, 1.5), (31.5, 11), (16.5, 11), (24, 3)], "a")
        g.ellipse(CX, 11.5, 15.5, 2.4, "a")
        g.outline().shade("a", "right", 2)
        g.draw([".m.", "mmm", ".m."], 23, 6)
    elif name == "crown":
        description = "корона с камнями"
        g.rect(15, 8, 32, 10, "m")
        for x in (15, 20, 24, 28, 32):
            g.poly([(x - 1.6, 8.5), (x + 0.5, 3), (x + 2.6, 8.5)], "m")
        g.outline().shade("m", "right", 1)
        for x in (18, 23, 24, 29):
            g.set(x, 9, "a")
    elif name == "visor":
        description = "футуристический визор на глазах"
        g.fill(lambda x, y: 13 <= x <= 34 and 19 <= y <= 23 - (abs(x - CX) > 8), "a")
        g.outline().shade("a", "down", 1)
        g.hline(15, 18, 20, "w").set(19, 21, "w")
    elif name == "pendant":
        description = "кулон на цепочке"
        g.line(18, 36, 24, 42, "m").line(29, 36, 24, 42, "m")
        g.draw([".a.", "aAa", ".a."], 23, 42)
        g.outline()
        g.replace("o", T)
        g.draw(["oao", "aAa", "oao"], 23, 42)
        g.set(23, 42, T).set(25, 42, T).set(23, 44, T).set(25, 44, T)
    elif name == "freckles":
        description = "веснушки на щеках"
        for x, y in [(16, 24), (18, 25), (17, 26), (19, 24), (29, 24), (31, 25), (30, 26), (28, 25)]:
            g.set(x, y, "S")
        extra["clip"] = "head"
    else:
        raise KeyError(name)
    return part(name, "accessory", description, g, **extra)


ACCESSORIES = ["glasses", "monocle", "eyepatch", "scar", "earring", "headband", "fedora", "wizard_hat",
               "crown", "visor", "pendant", "freckles"]


def build() -> dict[str, list[dict]]:
    return {
        "head": [make_head(n) for n in HEADS],
        "hair": [make_hair(n) for n in HAIR],
        "eyes": [make_eyes(n) for n in EYES],
        "brows": [make_brows(n) for n in BROWS],
        "mouth": [make_mouth(n) for n in MOUTHS],
        "facial_hair": [make_facial_hair(n) for n in FACIAL_HAIR],
        "outfit": [make_outfit(n) for n in OUTFITS],
        "accessory": [make_accessory(n) for n in ACCESSORIES],
    }
