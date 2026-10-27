"""Спрайты персонажей в полный рост 16×32 для карты (SPEC §5.8.3).

Вид сбоку, персонаж смотрит вправо (влево — зеркально в рантайме).
Кадры строятся из поз скелета: idle (2), walk (4), climb (2). Каждая деталь
рисуется отдельно для каждого кадра функцией от позы.

Id деталей совпадают с id деталей портрета того же слота: спрайт выводится
из PortraitSpec без дополнительных полей. Слоты: head, hair, outfit,
facial_hair, accessory (только головные уборы и то, что видно в 16×32).

Слои снизу вверх: hair.back → outfit → head → facial_hair → hair → accessory.
Все спрайты ставятся anchor-ом в REF — точку между ступнями на земле.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from px import T, Grid

W, H = 24, 40           # рабочий холст: запас сверху под шляпы и по бокам под волосы
OX, OY = 4, 8            # начало «коробки» 16×32 внутри холста
REF = (OX + 8, OY + 31)  # anchor: между ступнями, нижняя строка
SIZE = (16, 32)


@dataclass(frozen=True)
class Pose:
    bob: int                                  # смещение всего выше бёдер по вертикали
    legs: tuple[tuple[int, int], tuple[int, int]]   # (сдвиг стопы по x, подъём стопы) — дальняя, ближняя
    arms: tuple[tuple[int, int], tuple[int, int]]   # (dx, dy) кисти от нижней точки — дальняя, ближняя


POSES: dict[str, list[Pose]] = {
    "idle": [
        Pose(0, ((-1, 0), (1, 0)), ((-1, 0), (0, 0))),
        Pose(1, ((-1, 0), (1, 0)), ((-1, 0), (0, 0))),
    ],
    "walk": [
        Pose(0, ((-3, 0), (3, 0)), ((2, -1), (-2, -1))),
        Pose(-1, ((0, 0), (0, 2)), ((0, 0), (0, 0))),
        Pose(0, ((3, 0), (-3, 0)), ((-2, -1), (2, -1))),
        Pose(-1, ((0, 2), (0, 0)), ((0, 0), (0, 0))),
    ],
    "climb": [
        Pose(0, ((1, 0), (1, 3)), ((2, -5), (2, -10))),
        Pose(0, ((1, 3), (1, 0)), ((2, -10), (2, -5))),
    ],
}


def grid() -> Grid:
    return Grid(W, H)


def P(x: float, y: float) -> tuple[float, float]:
    """Координаты внутри коробки 16×32 → холст."""
    return OX + x, OY + y


def thick_line(g: Grid, a: tuple[float, float], b: tuple[float, float], c: str, width: int = 2) -> None:
    (x0, y0), (x1, y1) = a, b
    steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0)) * 2))
    for i in range(steps + 1):
        t = i / steps
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        g.rect(int(x), int(y), int(x) + width - 1, int(y), c)


# --- скелет -----------------------------------------------------------------------

HEAD_C = (8.5, 8.0)      # центр головы (без bob)
SHOULDER = (8, 14)
HIP_Y = 22
HAND_Y = 20
FOOT_Y = 31


def head_center(pose: Pose) -> tuple[float, float]:
    return HEAD_C[0], HEAD_C[1] + pose.bob


def leg_points(pose: Pose, i: int) -> tuple[tuple[float, float], tuple[float, float]]:
    hip_x = 7 if i == 0 else 8
    dx, lift = pose.legs[i]
    return P(hip_x, HIP_Y + pose.bob), P(hip_x + dx, FOOT_Y - 1 - lift)


def arm_points(pose: Pose, i: int) -> tuple[tuple[float, float], tuple[float, float]]:
    sx = SHOULDER[0] - (1 if i == 0 else 0)
    dx, dy = pose.arms[i]
    return P(sx, SHOULDER[1] + pose.bob), P(sx + dx, HAND_Y + pose.bob + dy)


# --- голова ------------------------------------------------------------------------

HEADS = {  # rx, ry, квадратность челюсти
    "oval": (3.6, 4.4, 0.0), "round": (3.9, 4.2, 0.0), "square": (3.8, 4.4, 0.6),
    "thin": (3.3, 4.6, 0.0), "heart": (3.8, 4.3, -0.3), "old": (3.6, 4.4, 0.0),
}


def draw_head(g: Grid, name: str, pose: Pose) -> None:
    rx, ry, square = HEADS[name]
    cx, cy = head_center(pose)
    X, Y = P(cx, cy)

    def inside(x: float, y: float) -> bool:
        nx, ny = (x - X) / rx, (y - Y) / ry
        if square > 0 and ny > 0.2:
            return abs(nx) <= 1 and ny <= 1 - 0.05 * (1 - square)
        return nx * nx + ny * ny <= 1
    g.fill(inside, "s")
    g.rect(int(X) - 1, int(Y + ry) - 1, int(X) + 1, int(Y + ry) + 1, "s", over=T)  # шея
    g.set(int(X + rx) + 1, int(Y) + 1, "s")  # нос
    g.outline()
    g.set(int(X) - 2, int(Y) + 1, "S")  # ухо
    g.set(int(X + rx) - 1, int(Y), "k")  # глаз
    if name == "old":
        g.set(int(X + rx) - 1, int(Y) + 1, "S")
    g.shade("s", "left", 1)


# --- причёски ------------------------------------------------------------------------

HAIR_IDS = ["short_messy", "short_neat", "crew_cut", "side_part", "long_straight", "long_braid", "ponytail",
            "bun", "curly", "afro", "mohawk", "bob", "balding", "hood"]


def draw_hair(front: Grid, back: Grid, name: str, pose: Pose) -> None:
    cx, cy = head_center(pose)
    X, Y = P(cx, cy)
    c = "c" if name == "hood" else "h"

    def cap(grow: float, hairline_front: float, hairline_back: float):
        def f(x: float, y: float) -> bool:
            if ((x - X) / (3.7 + grow)) ** 2 + ((y - Y) / (4.5 + grow)) ** 2 > 1:
                return False
            t = (x - X + 3) / 7  # 0 — затылок, 1 — лицо
            line = hairline_back + (hairline_front - hairline_back) * max(0.0, min(1.0, t))
            return y < Y + line
        return f

    if name in ("short_messy", "short_neat", "side_part", "long_straight", "long_braid", "ponytail", "bun", "bob"):
        front.fill(cap(0.8, -1.8, 2.5), c)
    if name == "short_messy":
        for i, x in enumerate(range(int(X) - 3, int(X) + 4, 2)):
            front.set(x, int(Y - 5.3) - (i % 2), c)
    elif name == "side_part":
        front.fill(lambda x, y: X + 1 <= x <= X + 4 and Y - 3 <= y <= Y - 1, c)
    elif name == "crew_cut":
        front.fill(cap(0.3, -2.2, 1.5), c)
        front.dither("h", "H", 1)
    elif name == "long_straight":
        back.fill(lambda x, y: X - 4.2 <= x <= X - 0.5 and Y <= y <= Y + 12.5 - (X - x) * 0.2, c)
    elif name == "long_braid":
        for i in range(5):
            back.ellipse(X - 3 - i * 0.15, Y + 4 + i * 2.2, 1.4, 1.3, c)
        back.set(int(X - 4), int(Y + 14), "a").set(int(X - 3), int(Y + 14), "a")
    elif name == "ponytail":
        thick_line(back, (X - 3.5, Y - 2), (X - 6, Y + 5), c, 2)
        front.set(int(X - 3), int(Y - 2), "a")
    elif name == "bun":
        front.ellipse(X - 2.5, Y - 4.8, 2.0, 1.8, c)
    elif name == "bob":
        front.fill(lambda x, y: X - 4.5 <= x <= X + 0.5 and Y - 2 <= y <= Y + 4, c)
        front.fill(lambda x, y: X + 0.5 < x <= X + 4.5 and Y - 4 <= y <= Y - 2, c)
    elif name == "curly":
        front.fill(cap(1.2, -2.6, 3.5), c)
        for a in range(150, 300, 25):  # кудри на затылке и макушке, не на лице
            front.ellipse(X + 4.4 * math.cos(math.radians(a)), Y + 4.8 * math.sin(math.radians(a)), 1.4, 1.4, c)
    elif name == "afro":
        back.ellipse(X - 0.5, Y - 1.5, 6.0, 5.8, c)
        front.fill(cap(0.8, -2.0, 2.0), c)
    elif name == "mohawk":
        front.fill(lambda x, y: abs(x - X + 0.5) <= 3 and Y - 8 <= y <= Y - 3.5 and ((x - X) / 3.8) ** 2 + ((y - Y + 2) / 6.4) ** 2 <= 1, c)
    elif name == "balding":
        front.fill(lambda x, y: x < X - 0.5 and Y - 1 <= y <= Y + 2 and ((x - X) / 4.5) ** 2 + ((y - Y) / 5) ** 2 <= 1, c)
    elif name == "hood":
        front.fill(lambda x, y: ((x - X + 0.5) / 4.8) ** 2 + ((y - Y) / 5.4) ** 2 <= 1 and not (x > X + 0.5 and Y - 2.5 < y < Y + 3.5), c)
        back.fill(lambda x, y: X - 5 <= x <= X + 1 and Y + 2 <= y <= Y + 8, c)

    for g in (front, back):
        g.outline()
        g.shade(c, "left", 1)


# --- наряды ------------------------------------------------------------------------

OUTFITS: dict[str, dict] = {
    # torso, sleeve, pants, shoes, hem (докуда полы/юбка; None — до бёдер), flare
    "detective_coat": dict(torso="c", sleeve="c", pants="C", shoes="k", hem=27, flare=1),
    "plate_armor": dict(torso="m", sleeve="m", pants="m", shoes="M", hem=None, flare=0),
    "mage_robe": dict(torso="c", sleeve="c", pants="C", shoes="k", hem=30, flare=2),
    "business_suit": dict(torso="c", sleeve="c", pants="c", shoes="k", hem=23, flare=0),
    "work_jacket": dict(torso="c", sleeve="c", pants="C", shoes="k", hem=23, flare=0),
    "dress": dict(torso="c", sleeve="s", pants="s", shoes="a", hem=26, flare=2),
    "scifi_armor": dict(torso="c", sleeve="c", pants="c", shoes="m", hem=None, flare=0),
    "rags": dict(torso="c", sleeve="s", pants="C", shoes="s", hem=24, flare=1),
    "peasant_tunic": dict(torso="c", sleeve="c", pants="C", shoes="k", hem=24, flare=1),
    "noble_coat": dict(torso="c", sleeve="c", pants="w", shoes="k", hem=26, flare=1),
    "leather_armor": dict(torso="c", sleeve="c", pants="C", shoes="k", hem=23, flare=0),
    "military_uniform": dict(torso="c", sleeve="c", pants="c", shoes="k", hem=23, flare=0),
}

DESCRIPTIONS = {
    "detective_coat": "плащ до колен", "plate_armor": "латы", "mage_robe": "мантия до пола",
    "business_suit": "костюм с галстуком", "work_jacket": "куртка", "dress": "платье",
    "scifi_armor": "броня со светящимися полосами", "rags": "лохмотья, босиком", "peasant_tunic": "рубаха с поясом",
    "noble_coat": "камзол и белые бриджи", "leather_armor": "кожаная броня и сапоги", "military_uniform": "мундир с эполетами",
}


def draw_outfit(g: Grid, name: str, pose: Pose) -> None:
    o = OUTFITS[name]
    b = pose.bob

    def limb_leg(i: int, far: bool) -> None:
        hip, foot = leg_points(pose, i)
        pants = o["pants"].upper() if far and o["pants"].islower() else o["pants"]
        thick_line(g, hip, foot, pants)
        fx, fy = int(foot[0]), int(foot[1]) + 1
        shoes = o["shoes"].upper() if far and o["shoes"].islower() else o["shoes"]
        g.rect(fx, fy, fx + 2, fy, shoes)
        if name in ("leather_armor", "military_uniform", "scifi_armor"):  # сапоги
            g.rect(int(foot[0]), int(foot[1]) - 2, int(foot[0]) + 1, int(foot[1]), shoes)

    def limb_arm(i: int, far: bool) -> None:
        shoulder, hand = arm_points(pose, i)
        sleeve = o["sleeve"].upper() if far and o["sleeve"].islower() else o["sleeve"]
        elbow = ((shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2)
        thick_line(g, shoulder, hand if sleeve != "s" else elbow, sleeve)
        if sleeve == "s" or name == "rags":
            thick_line(g, elbow, hand, "S" if far else "s")
        hx, hy = int(hand[0]), int(hand[1])
        g.rect(hx, hy, hx + 1, hy + 1, "S" if far else "s")

    limb_arm(0, far=True)
    limb_leg(0, far=True)

    # торс
    tx0, tx1 = OX + 6, OX + 10
    top, hip = OY + 13 + b, OY + HIP_Y + b
    g.rect(tx0, top, tx1, hip, o["torso"])
    if o["hem"]:
        hem = OY + o["hem"]
        g.fill(lambda x, y: hip <= y <= hem and tx0 - o["flare"] * (y - hip) / max(1, hem - hip) - 0.5 <= x <= tx1 + o["flare"] * (y - hip) / max(1, hem - hip) + 0.5, o["torso"])

    limb_leg(1, far=False)
    if o["hem"]:  # полы поверх ближней ноги
        hem = OY + o["hem"]
        g.fill(lambda x, y: hip <= y <= hem and tx0 - o["flare"] * (y - hip) / max(1, hem - hip) - 0.5 <= x <= tx1 + o["flare"] * (y - hip) / max(1, hem - hip) + 0.5, o["torso"])

    # детали
    if name == "detective_coat":
        g.vline(tx1, top + 1, OY + 26, "C").rect(tx0, top + 6, tx1, top + 6, "C")
        g.rect(tx0, top - 1, tx0 + 1, top, "c")
    elif name == "plate_armor":
        g.rect(tx0 + 2, top + 3, tx1, hip + 2, "c").vline(tx1, top + 3, hip + 2, "a")
        g.ellipse(OX + 8, top + 1, 2.4, 1.6, "m")
    elif name == "mage_robe":
        g.vline(tx1, top, OY + 30, "a").hline(tx0 - 2, tx1 + 2, OY + 30, "a")
    elif name == "business_suit":
        g.rect(tx1 - 1, top, tx1, top + 3, "w").vline(tx1, top + 1, top + 5, "a")
    elif name == "work_jacket":
        g.vline(tx1, top + 1, hip + 1, "m").rect(tx0, top, tx1, top, "a")
    elif name == "dress":
        g.rect(tx0, top, tx1, top, "a").hline(tx0 - 2, tx1 + 2, OY + 26, "a")
    elif name == "scifi_armor":
        g.vline(tx0 + 2, top + 1, hip, "a").rect(tx0, top, tx1, top + 1, "m")
    elif name == "rags":
        for x in range(tx0 - 1, tx1 + 2, 2):
            g.set(x, OY + 24, T)
        g.set(tx0 + 2, top + 4, "s")
    elif name == "peasant_tunic":
        g.rect(tx0, hip - 2, tx1, hip - 2, "a").set(tx1, top + 1, "w").set(tx1, top + 2, "w")
    elif name == "noble_coat":
        g.vline(tx1, top, OY + 26, "a").rect(tx1 - 1, top, tx1, top + 2, "w")
    elif name == "leather_armor":
        g.line(tx0, top, tx1, hip - 1, "a").set(tx0 + 2, top + 4, "m")
    elif name == "military_uniform":
        g.rect(tx0, hip - 1, tx1, hip - 1, "a").rect(tx0, top, tx0 + 2, top, "a").set(tx1, top + 3, "m").set(tx1, top + 6, "m")

    limb_arm(1, far=False)
    g.outline()


# --- растительность и головные уборы ---------------------------------------------------

def draw_facial_hair(g: Grid, name: str, pose: Pose) -> None:
    cx, cy = head_center(pose)
    X, Y = P(cx, cy)
    if name == "full_beard":
        g.fill(lambda x, y: X - 1 <= x <= X + 4 and Y + 1.5 <= y <= Y + 5 and ((x - X) / 4.2) ** 2 + ((y - Y) / 5.2) ** 2 <= 1.15, "h")
    elif name == "goatee":
        g.rect(int(X) + 2, int(Y) + 3, int(X) + 3, int(Y) + 5, "h")
    elif name == "mustache":
        g.rect(int(X) + 2, int(Y) + 2, int(X) + 4, int(Y) + 2, "h")
    else:
        return
    g.outline()


HEADWEAR = {
    "fedora": "шляпа", "wizard_hat": "колпак", "crown": "корона", "headband": "повязка",
    "visor": "визор", "glasses": "очки", "eyepatch": "повязка на глаз",
}


def draw_accessory(g: Grid, name: str, pose: Pose) -> None:
    cx, cy = head_center(pose)
    X, Y = P(cx, cy)
    top = int(Y - 4.5)
    if name == "fedora":
        g.rect(int(X) - 5, top + 1, int(X) + 5, top + 1, "a").rect(int(X) - 3, top - 3, int(X) + 3, top, "a")
        g.rect(int(X) - 3, top, int(X) + 3, top, "k")
        g.outline()
    elif name == "wizard_hat":
        g.poly([(X - 5, top + 2), (X + 5.5, top + 2), (X + 1, top - 6), (X - 2, top - 7)], "a")
        g.outline()
    elif name == "crown":
        g.rect(int(X) - 3, top - 1, int(X) + 3, top, "m")
        for x in range(int(X) - 3, int(X) + 4, 2):
            g.set(x, top - 2, "m")
        g.set(int(X), top, "a")
        g.outline()
    elif name == "headband":
        g.rect(int(X) - 4, top + 2, int(X) + 4, top + 2, "a").set(int(X) - 5, top + 3, "a").set(int(X) - 6, top + 4, "a")
    elif name == "visor":
        g.rect(int(X) + 1, int(Y) - 1, int(X) + 5, int(Y), "a")
        g.outline()
    elif name == "glasses":
        g.set(int(X + 3.5), int(Y) - 1, "o").set(int(X + 4.5), int(Y), "o").set(int(X + 2.5), int(Y), "o")
    elif name == "eyepatch":
        g.set(int(X + 2.6), int(Y), "k").line(int(X + 2), int(Y) - 1, int(X) - 3, int(Y) - 3, "k")


# --- сборка ---------------------------------------------------------------------------

def frames(draw, *args) -> dict[str, list[dict]]:
    out = {}
    for anim, poses in POSES.items():
        out[anim] = []
        for pose in poses:
            g = grid()
            draw(g, *args, pose)
            out[anim].append(g.sprite(REF))
    return out


def hair_part(name: str) -> dict:
    front_frames, back_frames = {}, {}
    for anim, poses in POSES.items():
        front_frames[anim], back_frames[anim] = [], []
        for pose in poses:
            f, b = grid(), grid()
            draw_hair(f, b, name, pose)
            front_frames[anim].append(f.sprite(REF))
            back_frames[anim].append(b.sprite(REF))
    part = {"id": name, "slot": "walker_hair", "description": name, "frames": front_frames}
    if any(sp["w"] for sps in back_frames.values() for sp in sps):
        part["back_frames"] = back_frames
    return part


def build() -> dict[str, list[dict]]:
    return {
        "head": [{"id": n, "slot": "walker_head", "description": n, "frames": frames(draw_head, n)} for n in HEADS],
        "hair": [hair_part(n) for n in HAIR_IDS],
        "outfit": [{"id": n, "slot": "walker_outfit", "description": DESCRIPTIONS[n], "frames": frames(draw_outfit, n)} for n in OUTFITS],
        "facial_hair": [{"id": n, "slot": "walker_facial_hair", "description": n, "frames": frames(draw_facial_hair, n)}
                        for n in ("full_beard", "goatee", "mustache", "stubble")],
        "accessory": [{"id": n, "slot": "walker_accessory", "description": d, "frames": frames(draw_accessory, n)} for n, d in HEADWEAR.items()],
    }
