"""Библиотека деталей: целостность, «дырки» и съехавшие слои, проверка внешности в играх."""

import importlib.util
import itertools
import json
from pathlib import Path

import pytest

from app.engine.art import LIBRARY_DIR, load_library, repair_art
from app.engine.validator import validate

from .conftest import scene

EMOTIONS = ["neutral", "angry", "sad", "happy", "scared", "surprised"]
PORTRAIT_CHARS = set(".oswkmhcaerSHCAEWMR")
CREATURE_CHARS = set(".ocaewkmCAWM")
BACKGROUND_CHARS = set(".ofFgGpPqQvVaAlnNwkmM")
CHARS_BY_DIR = {"portrait": PORTRAIT_CHARS, "creature": CREATURE_CHARS, "background": BACKGROUND_CHARS}


def raw_parts() -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for file in LIBRARY_DIR.rglob("*.json"):
        if file.name in ("palettes.json", "layout.json"):
            continue
        for p in json.loads(file.read_text(encoding="utf-8")):
            p["_dir"] = file.parent.name
            out.setdefault(p["slot"], {})[p["id"]] = p
    return out


PARTS = raw_parts()
LAYOUT = json.loads((LIBRARY_DIR / "layout.json").read_text(encoding="utf-8"))


# --- целостность библиотеки ---


def sprites_of(part: dict):
    yield "", part
    for name, v in part.get("variants", {}).items():
        yield f".variants.{name}", v
    if "back" in part:
        yield ".back", part["back"]


def test_minimum_library_size():
    """Минимальная библиотека из SPEC §5.7.2–5.7.4."""
    minimum = {"head": 6, "hair": 14, "eyes": 6, "brows": 5, "mouth": 6, "facial_hair": 4, "outfit": 12,
               "accessory": 12, "creature_body": 10, "creature_feature": 10, "sky": 6, "far": 10, "prop": 25, "ground": 6}
    assert {slot: len(PARTS[slot]) >= n for slot, n in minimum.items()} == {slot: True for slot in minimum}
    palettes = load_library().palettes
    assert len(palettes["skin_tones"]) >= 8 and len(palettes["hair_colors"]) >= 12
    assert len(palettes["cloth_colors"]) >= 16 and len(palettes["mood_palettes"]) >= 8


def test_sprites_are_well_formed():
    bad = []
    for slot, parts in PARTS.items():
        for pid, part in parts.items():
            allowed = CHARS_BY_DIR[part["_dir"]]
            for suffix, sp in sprites_of(part):
                name = f"{slot}:{pid}{suffix}"
                if len(sp["pixels"]) != sp["h"] or any(len(r) != sp["w"] for r in sp["pixels"]):
                    bad.append(f"{name}: размер не совпадает с w×h")
                if extra := set("".join(sp["pixels"])) - allowed:
                    bad.append(f"{name}: недопустимые символы {sorted(extra)}")
    assert bad == []


def test_emotion_variants_are_complete():
    for slot in ("eyes", "brows", "mouth"):
        for pid, part in PARTS[slot].items():
            assert sorted(part["variants"]) == sorted(EMOTIONS), f"{slot}:{pid}"


def test_emotions_actually_differ():
    """Эмоция должна менять картинку хотя бы в одной из деталей лица."""
    for emotion in EMOTIONS[1:]:
        changed = any(
            part["variants"][emotion]["pixels"] != part["variants"]["neutral"]["pixels"]
            for slot in ("eyes", "brows", "mouth") for part in PARTS[slot].values()
        )
        assert changed, emotion


def test_creature_points_and_attachments():
    for pid, body in PARTS["creature_body"].items():
        assert set(body["points"]) == {"head_top", "back", "face", "mouth"}, pid
    for pid, feature in PARTS["creature_feature"].items():
        assert feature["attach"] in {"head_top", "back", "face", "mouth"}, pid
        assert feature["layer"] in {"back", "front"}, pid


# --- композиция: дырки и съехавшие слои ---

W, H = LAYOUT["portrait"]["w"], LAYOUT["portrait"]["h"]
REF = LAYOUT["portrait"]["ref"]


def cells(sprite: dict, at=REF):
    ox, oy = at[0] - sprite["anchor"][0], at[1] - sprite["anchor"][1]
    for y, row in enumerate(sprite["pixels"]):
        for x, ch in enumerate(row):
            if ch != ".":
                yield ox + x, oy + y, ch


_MASKS: dict[int, int] = {}


def sprite_mask(sp: dict) -> int:
    """Непрозрачные пиксели спрайта на холсте как битовая маска (бит y*W+x)."""
    key = id(sp)
    if key not in _MASKS:
        bits = 0
        for x, y, _ in cells(sp):
            if 0 <= x < W and 0 <= y < H:
                bits |= 1 << (y * W + x)
        _MASKS[key] = bits
    return _MASKS[key]


def opaque(*sprites) -> int:
    mask = 0
    for sp in sprites:
        mask |= sprite_mask(sp)
    return mask


FULL = (1 << (W * H)) - 1
LEFT_EDGE = sum(1 << (y * W) for y in range(H))
RIGHT_EDGE = LEFT_EDGE << (W - 1)
BORDER = ((1 << W) - 1) | (((1 << W) - 1) << (W * (H - 1))) | LEFT_EDGE | RIGHT_EDGE


def holes(mask: int) -> list[tuple[int, int]]:
    """Прозрачные пиксели, недостижимые от края холста, — дырки внутри фигуры.

    Заливка от края по прозрачным пикселям на битовых масках (4-связность).
    """
    free = FULL & ~mask
    reached = BORDER & free
    while True:
        grow = reached | (reached << W) | (reached >> W) | ((reached << 1) & ~LEFT_EDGE) | ((reached >> 1) & ~RIGHT_EDGE)
        grow &= free
        if grow == reached:
            break
        reached = grow
    left = free & ~reached
    return [(i % W, i // W) for i in range(W * H) if left >> i & 1]


def hair_layers(hid):
    if hid is None:
        return []
    hair = PARTS["hair"][hid]
    return [hair.get("back"), hair] if "back" in hair else [hair]


@pytest.mark.parametrize("head", sorted(PARTS["head"]))
def test_no_holes_in_portrait_combinations(head):
    head_sp = PARTS["head"][head]
    bad = []
    for hair, outfit in itertools.product([None, *sorted(PARTS["hair"])], sorted(PARTS["outfit"])):
        layers = [*hair_layers(hair), PARTS["outfit"][outfit], head_sp]
        for extra in [None, *PARTS["facial_hair"].values(), *PARTS["accessory"].values()]:
            plain = [extra] if extra and not extra.get("clip") else []
            if found := holes(opaque(*layers, *plain)):
                bad.append(f"{hair}/{outfit}/{extra and extra['id']}: {sorted(found)[:4]}")
    assert bad == [], bad[:10]


@pytest.mark.parametrize("head", sorted(PARTS["head"]))
def test_face_features_sit_on_skin(head):
    skin = {(x, y) for x, y, ch in cells(PARTS["head"][head]) if ch in "sS"}
    bad = []
    for slot in ("eyes", "brows", "mouth"):
        for pid, part in PARTS[slot].items():
            for emotion, sp in part["variants"].items():
                off = [(x, y) for x, y, _ in cells(sp) if (x, y) not in skin]
                if off:
                    bad.append(f"{slot}:{pid}:{emotion} вне кожи: {off[:4]}")
    assert bad == []


# --- проверка внешности в играх ---


def error_paths(data) -> dict[str, str]:
    return {i.path: i.message for i in validate(data).errors}


def test_unknown_portrait_part_and_color(demo):
    demo["hero"]["appearance"]["hair"] = "dreadlocks"
    demo["characters"][0]["appearance"]["outfit_color"] = "ultramarine"
    errors = error_paths(demo)
    assert errors["hero.appearance.hair"].startswith("неизвестная деталь слота hair: 'dreadlocks'. Допустимо: short_messy")
    assert "characters[0].appearance.outfit_color" in errors


def test_hair_none_is_allowed(demo):
    assert demo["characters"][2]["appearance"]["hair"] == "none"
    assert validate(demo).ok


def test_unknown_creature_feature_and_background_parts(demo):
    demo["enemies"][0]["appearance"]["features"] = ["tentacles"]
    bg = scene(demo, "pier")["background"]
    bg["props"][0]["id"] = "anchor"
    bg["mood_palette"] = "sepia"
    errors = error_paths(demo)
    assert "enemies[0].appearance.features[0]" in errors
    assert "scenes[0].background.props[0].id" in errors
    assert "scenes[0].background.mood_palette" in errors


def test_setting_mismatch_is_warning(demo):
    bg = scene(demo, "archive")["background"]
    bg["sky"] = "moon"
    bg["props"].append({"id": "pine", "x": 60})
    report = validate(demo)
    assert report.ok
    assert {w.path for w in report.warnings} == {"scenes[2].background.sky", "scenes[2].background.props[4].id"}


def test_repair_substitutes_defaults(demo):
    demo["hero"]["appearance"]["hair"] = "dreadlocks"
    demo["enemies"][2]["appearance"]["body"] = "kraken"
    report = validate(demo)
    assert not report.ok

    warnings = repair_art(report.game, load_library())
    assert [w.path for w in warnings] == ["hero.appearance.hair", "enemies[2].appearance.body"]
    assert report.game.hero.appearance.hair == "short_messy"
    assert validate(report.game).ok


def test_art_check_can_be_disabled(demo):
    demo["hero"]["appearance"]["hair"] = "dreadlocks"
    assert validate(demo, art=None).ok


# --- каталог ---


def test_catalog_is_in_sync():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_catalog.py"
    spec = importlib.util.spec_from_file_location("build_catalog", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.CATALOG_PATH.read_text(encoding="utf-8") == mod.render(load_library()), (
        "pixelart/catalog.md устарел: запусти python scripts/build_catalog.py"
    )


def test_hole_detector_finds_enclosed_pixel():
    ring = {"w": 3, "h": 3, "anchor": [1, 1], "pixels": ["ooo", "o.o", "ooo"]}
    notch = {"w": 3, "h": 3, "anchor": [1, 1], "pixels": ["o.o", "o.o", "ooo"]}
    assert holes(opaque(ring)) == [tuple(REF)]
    assert holes(opaque(notch)) == []
