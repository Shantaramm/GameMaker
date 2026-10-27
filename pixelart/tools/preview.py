"""Превью деталей для разработки (Pillow). Повторяет логику frontend/src/pixel/.

Эталон рендера — TypeScript-движок; этот файл нужен только чтобы быстро
посмотреть детали без запуска фронта:
    python pixelart/tools/preview.py out.png
"""

from __future__ import annotations

import colorsys
import json
import random
import sys
from pathlib import Path

from PIL import Image

LIB = Path(__file__).resolve().parents[1] / "library"
PORTRAIT_LAYERS = ["back_hair", "outfit", "head", "eyes", "brows", "facial_hair", "mouth", "front_hair", "accessory"]


def load() -> tuple[dict, dict]:
    palettes = json.loads((LIB / "palettes.json").read_text())
    parts: dict[str, dict[str, dict]] = {}
    for f in LIB.rglob("*.json"):
        if f.name in ("palettes.json", "layout.json"):
            continue
        for p in json.loads(f.read_text()):
            parts.setdefault(p["slot"], {})[p["id"]] = p
    return palettes, parts


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(rgb, k: float = 0.75):
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    return tuple(round(v * 255) for v in colorsys.hls_to_rgb(h, l * k, s))


def mix(a, b, t: float):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def portrait_colors(spec: dict, pal: dict) -> dict:
    base = {k: hex_rgb(v) for k, v in pal["fixed"].items()}
    base.update(
        s=hex_rgb(pal["skin_tones"][spec["skin"]]),
        h=hex_rgb(pal["hair_colors"][spec["hair_color"]]),
        e=hex_rgb(pal["eye_colors"][spec["eye_color"]]),
        c=hex_rgb(pal["cloth_colors"][spec["outfit_color"]]),
        a=hex_rgb(pal["cloth_colors"][spec["accent_color"]]),
    )
    base["r"] = mix(base["s"], (168, 68, 60), 0.45)
    return base


def resolve(ch: str, colors: dict):
    if ch in colors:
        return colors[ch]
    low = ch.lower()
    if low in colors:
        return shade(colors[low])
    raise KeyError(ch)


def blit(img: Image.Image, sprite: dict, at: tuple[int, int], colors: dict, mask=None, record=None) -> None:
    ax, ay = sprite["anchor"]
    ox, oy = at[0] - ax, at[1] - ay
    for y, row in enumerate(sprite["pixels"]):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px, py = ox + x, oy + y
            if not (0 <= px < img.width and 0 <= py < img.height):
                continue
            if mask is not None and (px, py) not in mask:
                continue
            img.putpixel((px, py), resolve(ch, colors))
            if record is not None and ch in "sS":
                record.add((px, py))


def render_portrait(spec: dict, emotion: str, pal: dict, parts: dict) -> Image.Image:
    colors = portrait_colors(spec, pal)
    img = Image.new("RGB", (48, 48), hex_rgb(pal["cloth_colors"][spec["bg_color"]]))
    ref = (24, 24)
    head_mask: set = set()
    hair = parts["hair"].get(spec["hair"]) if spec["hair"] != "none" else None

    def pick(slot, pid):
        p = parts[slot][pid]
        return p.get("variants", {}).get(emotion, p)

    layers = []
    if hair and "back" in hair:
        layers.append((hair["back"], None))
    layers.append((parts["outfit"][spec["outfit"]], None))
    layers.append(("HEAD", None))
    layers.append((pick("eyes", spec["eyes"]), None))
    layers.append((pick("brows", spec["brows"]), None))
    if spec.get("facial_hair"):
        layers.append((parts["facial_hair"][spec["facial_hair"]], "fh"))
    layers.append((pick("mouth", spec["mouth"]), None))
    if hair:
        layers.append((hair, None))
    for acc in spec.get("accessory", []):
        layers.append((parts["accessory"][acc], "acc"))

    for sprite, _ in layers:
        if sprite == "HEAD":
            blit(img, parts["head"][spec["head"]], ref, colors, record=head_mask)
            continue
        mask = head_mask if sprite.get("clip") == "head" else None
        blit(img, sprite, ref, colors, mask=mask)
    return img


def render_creature(spec: dict, pal: dict, parts: dict) -> Image.Image:
    cloth = pal["cloth_colors"]
    colors = {k: hex_rgb(v) for k, v in pal["fixed"].items()}
    colors.update(c=hex_rgb(cloth[spec["color"]]), a=hex_rgb(cloth[spec["accent_color"]]))
    colors["e"] = mix(colors["a"], (255, 255, 255), 0.45)
    img = Image.new("RGB", (64, 64), (40, 36, 48))
    body = parts["creature_body"][spec["body"]]
    ox, oy = 32 - body["anchor"][0], 32 - body["anchor"][1]
    feats = [parts["creature_feature"][f] for f in spec.get("features", [])]

    def place(f):
        px_, py_ = body["points"][f["attach"]]
        blit(img, f, (ox + px_, oy + py_), colors)

    for f in feats:
        if f["layer"] == "back":
            place(f)
    blit(img, body, (32, 32), colors)
    for f in feats:
        if f["layer"] != "back":
            place(f)
    return img


TIME_TINT = {"day": None, "dusk": ((224, 112, 64), 0.25, 0.85), "night": ((24, 32, 74), 0.35, 0.55)}
UNTINTED = set("lwn")


def tint(rgb, time: str):
    t = TIME_TINT[time]
    if t is None:
        return rgb
    target, amount, light = t
    return shade(mix(rgb, target, amount), light)


def render_background(spec: dict, pal: dict, parts: dict, seed: int = 1) -> Image.Image:
    mood = pal["mood_palettes"][spec["mood_palette"]]
    top, bottom = (hex_rgb(c) for c in mood["sky"][spec["time"]])
    img = Image.new("RGB", (160, 90))
    bands = 7
    for y in range(90):
        t = min(1.0, y / 72)
        k = min(bands - 1, int(t * bands))
        # дизеринг на границе полос
        if (y * bands / 72) % 1 > 0.75 and k < bands - 1:
            pass
        for x in range(160):
            kk = k + (1 if (y * bands / 72) % 1 > 0.8 and (x + y) % 2 == 0 and k < bands - 1 else 0)
            img.putpixel((x, y), mix(top, bottom, kk / (bands - 1)))
    base = {k: hex_rgb(v) for k, v in pal["fixed"].items()}
    base.update({k: hex_rgb(v) for k, v in mood["colors"].items()})
    colors = {}
    for ch in "ofFgGpPqQvVaAkwmM":
        colors[ch] = tint(resolve(ch, base), spec["time"])
    colors["l"] = base["l"]
    colors["n"] = mix(bottom, (255, 255, 255), 0.45)
    colors["N"] = shade(mix(top, bottom, 0.5), 0.8)
    rng = random.Random(seed)
    if spec["setting"] == "outdoor" and spec.get("sky"):
        sky = parts["sky"][spec["sky"]]
        for _ in range(sky.get("stars", 0) if spec["time"] != "day" else 0):
            img.putpixel((rng.randrange(160), rng.randrange(60)), (230, 230, 240) if rng.random() < 0.7 else (160, 160, 190))
        blit(img, sky, (0, 0), colors)
    blit(img, parts["far"][spec["far"]], (0, 0), colors)
    blit(img, parts["ground"][spec["ground"]], (0, 0), colors)
    for p in spec.get("props", []):
        blit(img, parts["prop"][p["id"]], (p["x"], 82), colors)
    return img


WALKER_REF = (12, 39)


def render_walker(spec: dict, anim: str, i: int, pal: dict, parts: dict, bg=(50, 46, 60)) -> Image.Image:
    colors = portrait_colors(spec, pal)
    img = Image.new("RGB", (24, 40), bg)
    frame = lambda p: p["frames"][anim][i]
    hair = parts["walker_hair"].get(spec["hair"]) if spec["hair"] != "none" else None
    if hair and "back_frames" in hair:
        blit(img, hair["back_frames"][anim][i], WALKER_REF, colors)
    blit(img, frame(parts["walker_outfit"][spec["outfit"]]), WALKER_REF, colors)
    blit(img, frame(parts["walker_head"][spec["head"]]), WALKER_REF, colors)
    if spec.get("facial_hair"):
        blit(img, frame(parts["walker_facial_hair"][spec["facial_hair"]]), WALKER_REF, colors)
    if hair:
        blit(img, frame(hair), WALKER_REF, colors)
    for acc in spec.get("accessory", []):
        if acc in parts["walker_accessory"]:
            blit(img, frame(parts["walker_accessory"][acc]), WALKER_REF, colors)
    return img


def random_spec(rng: random.Random, pal: dict, parts: dict) -> dict:
    pick = lambda xs: rng.choice(sorted(xs))
    spec = {
        "head": pick(parts["head"]), "skin": pick(pal["skin_tones"]),
        "hair": pick(list(parts["hair"]) + ["none"]), "hair_color": pick(pal["hair_colors"]),
        "eyes": pick(parts["eyes"]), "eye_color": pick(pal["eye_colors"]),
        "brows": pick(parts["brows"]), "mouth": pick(parts["mouth"]),
        "outfit": pick(parts["outfit"]), "outfit_color": pick(pal["cloth_colors"]),
        "accent_color": pick(pal["cloth_colors"]), "bg_color": pick(pal["cloth_colors"]),
        "accessory": rng.sample(sorted(parts["accessory"]), rng.choice([0, 0, 1, 1, 2])),
    }
    if rng.random() < 0.3:
        spec["facial_hair"] = pick(parts["facial_hair"])
    return spec


def sheet(images: list[Image.Image], cols: int, scale: int = 4, gap: int = 2) -> Image.Image:
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * (w * scale + gap), rows * (h * scale + gap)), (30, 30, 30))
    for i, im in enumerate(images):
        out.paste(im.resize((w * scale, h * scale), Image.NEAREST), ((i % cols) * (w * scale + gap), (i // cols) * (h * scale + gap)))
    return out


BASE = {"head": "oval", "skin": "fair", "hair": "short_messy", "hair_color": "brown", "eyes": "round",
        "eye_color": "blue", "brows": "straight", "mouth": "thin", "outfit": "work_jacket",
        "outfit_color": "slate", "accent_color": "gold", "bg_color": "cream", "accessory": []}


def variations(slot_key: str, ids, pal, parts, **over) -> list[Image.Image]:
    out = []
    for pid in ids:
        spec = {**BASE, **over, slot_key: pid}
        out.append(render_portrait(spec, "neutral", pal, parts))
    return out


if __name__ == "__main__":
    pal, parts = load()
    mode = sys.argv[2] if len(sys.argv) > 2 else "random"
    rng = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    if mode == "tilesets":
        imgs = []
        for ts in sorted(parts["tileset"].values(), key=lambda x: x["id"]):
            mood = {"town_street": "cold_sea", "forest": "verdant", "cave": "violet_dread", "ship": "neon"}.get(ts["id"], "warm_candle")
            base = {k: hex_rgb(v) for k, v in pal["fixed"].items()}
            base.update({k: hex_rgb(v) for k, v in pal["mood_palettes"][mood]["colors"].items()})
            sky = [hex_rgb(c) for c in pal["mood_palettes"][mood]["sky"]["day"]]
            base["n"] = mix(sky[1], (255, 255, 255), 0.45)
            tl, img = ts["tiles"], Image.new("RGB", (160, 80), sky[0])
            for x in range(10):
                for y in range(4):
                    if "wall" in tl:
                        blit(img, tl["wall"], (x * 16, (y + 1) * 16), base)
                blit(img, tl["floor"], (x * 16, 80), base)
                if x < 6:
                    blit(img, tl["slab"], (x * 16, 32), base)
            for y in (48, 64):
                blit(img, tl["edge"], (0, y), base)
                blit(img, tl["ladder"], (96, y), base)
            for k, name in enumerate(("door", "door_open", "door_locked")):
                blit(img, tl[name], (16 + 16 * k, 64), base)
            for k, d in enumerate(ts["decor"].values()):
                blit(img, d, (64 + k * 16 if k < 2 else 112 + (k - 2) * 16, 40 if d["wall"] else 64), base)
            imgs.append(img)
        cols = 2
    elif mode == "icons":
        tiers = pal["icon_tiers"]
        imgs = []
        for t_ in ("1", "3", "5"):
            colors = {k: hex_rgb(v) for k, v in pal["fixed"].items()}
            colors.update({k: hex_rgb(v) for k, v in pal["icon_fixed"].items()})
            colors["c"] = hex_rgb(tiers[t_])
            for ic in sorted(parts["icon"].values(), key=lambda x: x["id"]):
                img = Image.new("RGB", (16, 16), (60, 54, 70))
                blit(img, ic, (0, 0), colors)
                imgs.append(img)
        cols = 13
    elif mode == "walkers":
        imgs = []
        for k in range(10):
            spec = random_spec(rng, pal, parts)
            imgs.append(render_portrait(spec, "neutral", pal, parts).crop((4, 4, 44, 44)).resize((24, 24)).resize((24, 40)))
            for anim, n in (("idle", 2), ("walk", 4), ("climb", 2)):
                imgs += [render_walker(spec, anim, i, pal, parts) for i in range(n)]
        cols = 9
    elif mode == "backgrounds":
        moods = sorted(pal["mood_palettes"])
        props = sorted(parts["prop"])
        imgs = []
        for i, far in enumerate(sorted(parts["far"])):
            setting = parts["far"][far]["setting"]
            for time in ("day", "night"):
                spec = {"setting": setting, "time": time, "far": far,
                        "sky": sorted(parts["sky"])[(i + (time == "night") * 2) % 6],
                        "ground": sorted(parts["ground"])[i % 6], "mood_palette": moods[i % 8],
                        "props": [{"id": props[(i * 5 + j * 3) % 25], "x": 20 + j * 40} for j in range(4)]}
                imgs.append(render_background(spec, pal, parts, i))
        cols = 4
    elif mode == "props":
        imgs = []
        pr = sorted(parts["prop"])
        for i in range(0, 25, 5):
            spec = {"setting": "indoor", "time": "day", "far": "room_wall", "ground": "planks", "mood_palette": "warm_candle",
                    "props": [{"id": pr[j], "x": 16 + (j - i) * 32} for j in range(i, min(i + 5, 25))]}
            imgs.append(render_background(spec, pal, parts))
        cols = 1
    elif mode == "creatures":
        cl = sorted(pal["cloth_colors"])
        feats = sorted(parts["creature_feature"])
        imgs = []
        for i, b in enumerate(sorted(parts["creature_body"])):
            imgs.append(render_creature({"body": b, "color": cl[i * 3 % len(cl)], "accent_color": cl[(i * 7 + 5) % len(cl)]}, pal, parts))
            imgs.append(render_creature({"body": b, "color": cl[(i * 5 + 2) % len(cl)], "accent_color": cl[(i * 3 + 9) % len(cl)],
                                         "features": [feats[i], feats[(i + 3) % 10], feats[(i + 6) % 10]]}, pal, parts))
        cols = 6
    elif mode == "random":
        imgs = [render_portrait(random_spec(rng, pal, parts), "neutral", pal, parts) for _ in range(20)]
        cols = 5
    elif mode == "emotions":
        imgs = []
        for eyes in sorted(parts["eyes"]):
            for e in ["neutral", "angry", "sad", "happy", "scared", "surprised"]:
                spec = {**BASE, "eyes": eyes, "mouth": ["thin", "full", "small", "wide", "smirk", "stern"][sorted(parts["eyes"]).index(eyes)],
                        "brows": sorted(parts["brows"])[sorted(parts["eyes"]).index(eyes) % 5]}
                imgs.append(render_portrait(spec, e, pal, parts))
        cols = 6
    else:
        slot = mode
        key = {"hair": "hair", "head": "head", "outfit": "outfit", "accessory": "accessory", "facial_hair": "facial_hair"}[slot]
        ids = sorted(parts[slot])
        if slot == "accessory":
            imgs = [render_portrait({**BASE, "accessory": [a]}, "neutral", pal, parts) for a in ids]
        elif slot == "facial_hair":
            imgs = variations("facial_hair", ids, pal, parts) + variations("facial_hair", ids, pal, parts, head="thin")
        elif slot == "head":
            imgs = variations("head", ids, pal, parts, hair="none") + variations("head", ids, pal, parts)
        else:
            imgs = variations(key, ids, pal, parts) + variations(key, ids, pal, parts, head="thin", hair_color="blonde", hair="none" if slot != "hair" else "x") if slot != "hair" else variations(key, ids, pal, parts) + variations(key, ids, pal, parts, head="round", hair_color="black")
        cols = 7
    sheet(imgs, cols).save(sys.argv[1])
    print("saved", sys.argv[1], len(imgs))
