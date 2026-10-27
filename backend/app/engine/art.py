"""Библиотека пиксельных деталей на стороне бэкенда (SPEC §5.7, §6.7).

Бэкенд не рисует: ему нужны только id деталей по слотам и имена цветов,
чтобы проверять внешность из ответа LLM и собирать каталог для промптов.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator

from . import schema as s
from .issues import Issue, format_path

LIBRARY_DIR = Path(__file__).resolve().parents[3] / "pixelart" / "library"

PORTRAIT_PARTS = {
    "head": "head", "hair": "hair", "eyes": "eyes", "brows": "brows",
    "mouth": "mouth", "facial_hair": "facial_hair", "outfit": "outfit",
}
PORTRAIT_COLORS = {
    "skin": "skin_tones", "hair_color": "hair_colors", "eye_color": "eye_colors",
    "outfit_color": "cloth_colors", "accent_color": "cloth_colors", "bg_color": "cloth_colors",
}
NO_HAIR = "none"


@dataclass
class PartInfo:
    id: str
    slot: str
    description: str
    setting: str | None = None


@dataclass
class ArtLibrary:
    parts: dict[str, dict[str, PartInfo]] = field(default_factory=dict)  # slot → id → деталь
    palettes: dict[str, dict[str, str]] = field(default_factory=dict)  # группа → имя → описание или hex

    def has_part(self, slot: str, ident: str) -> bool:
        return ident in self.parts.get(slot, {})

    def has_color(self, group: str, name: str) -> bool:
        return name in self.palettes.get(group, {})

    def default_part(self, slot: str) -> str:
        return next(iter(self.parts[slot]))

    def default_color(self, group: str) -> str:
        return next(iter(self.palettes[group]))


@lru_cache(maxsize=4)
def load_library(path: Path = LIBRARY_DIR) -> ArtLibrary:
    lib = ArtLibrary()
    palettes = json.loads((path / "palettes.json").read_text(encoding="utf-8"))
    for group, values in palettes.items():
        if group == "fixed":
            continue
        lib.palettes[group] = {
            name: (v["description"] if isinstance(v, dict) else v) for name, v in values.items()
        }
    for file in sorted(path.rglob("*.json")):
        if file.name in ("palettes.json", "layout.json"):
            continue
        for part in json.loads(file.read_text(encoding="utf-8")):
            lib.parts.setdefault(part["slot"], {})[part["id"]] = PartInfo(
                part["id"], part["slot"], part["description"], part.get("setting"),
            )
    return lib


# --- обход ссылок на графику в игре -------------------------------------------

@dataclass
class ArtRef:
    path: str
    kind: str  # "part" | "color"
    key: str  # слот детали или группа палитры
    value: str
    replace: Callable[[str], None]


def _attr_setter(obj, attr: str) -> Callable[[str], None]:
    return lambda v: setattr(obj, attr, v)


def _item_setter(lst: list, index: int) -> Callable[[str], None]:
    return lambda v: lst.__setitem__(index, v)


def _portrait_refs(spec: s.PortraitSpec, path: str) -> Iterator[ArtRef]:
    for attr, slot in PORTRAIT_PARTS.items():
        value = getattr(spec, attr)
        if value is None or (attr == "hair" and value == NO_HAIR):
            continue
        yield ArtRef(format_path(path, attr), "part", slot, value, _attr_setter(spec, attr))
    for i, acc in enumerate(spec.accessory):
        yield ArtRef(format_path(path, "accessory", i), "part", "accessory", acc, _item_setter(spec.accessory, i))
    for attr, group in PORTRAIT_COLORS.items():
        yield ArtRef(format_path(path, attr), "color", group, getattr(spec, attr), _attr_setter(spec, attr))


def _creature_refs(spec: s.CreatureSpec, path: str) -> Iterator[ArtRef]:
    yield ArtRef(format_path(path, "body"), "part", "creature_body", spec.body, _attr_setter(spec, "body"))
    for i, f in enumerate(spec.features):
        yield ArtRef(format_path(path, "features", i), "part", "creature_feature", f, _item_setter(spec.features, i))
    for attr in ("color", "accent_color"):
        yield ArtRef(format_path(path, attr), "color", "cloth_colors", getattr(spec, attr), _attr_setter(spec, attr))


def _background_refs(spec: s.BackgroundSpec, path: str) -> Iterator[ArtRef]:
    if spec.sky is not None:
        yield ArtRef(format_path(path, "sky"), "part", "sky", spec.sky, _attr_setter(spec, "sky"))
    yield ArtRef(format_path(path, "far"), "part", "far", spec.far, _attr_setter(spec, "far"))
    yield ArtRef(format_path(path, "ground"), "part", "ground", spec.ground, _attr_setter(spec, "ground"))
    for i, prop in enumerate(spec.props):
        yield ArtRef(format_path(path, "props", i, "id"), "part", "prop", prop.id, _attr_setter(prop, "id"))
    yield ArtRef(format_path(path, "mood_palette"), "color", "mood_palettes", spec.mood_palette, _attr_setter(spec, "mood_palette"))


def iter_art_refs(game: s.Game) -> Iterator[ArtRef]:
    yield from _portrait_refs(game.hero.appearance, "hero.appearance")
    for i, c in enumerate(game.characters):
        yield from _portrait_refs(c.appearance, format_path("characters", i, "appearance"))
    for i, e in enumerate(game.enemies):
        path = format_path("enemies", i, "appearance")
        if isinstance(e.appearance, s.CreatureSpec):
            yield from _creature_refs(e.appearance, path)
        else:
            yield from _portrait_refs(e.appearance, path)
    for i, item in enumerate(game.items):
        yield ArtRef(format_path("items", i, "icon"), "part", "icon", item.icon, _attr_setter(item, "icon"))
    for i, t in enumerate(game.tactics):
        yield ArtRef(format_path("tactics", i, "icon"), "part", "icon", t.icon, _attr_setter(t, "icon"))
    for i, loc in enumerate(game.locations):
        path = format_path("locations", i)
        yield ArtRef(format_path(path, "theme"), "part", "tileset", loc.theme, _attr_setter(loc, "theme"))
        yield from _background_refs(loc.background, format_path(path, "background"))
        for j, obj in enumerate(loc.objects):
            if isinstance(obj, (s.Chest, s.Thing)):
                yield ArtRef(format_path(path, "objects", j, "look"), "part", "prop", obj.look, _attr_setter(obj, "look"))


# --- проверка и подстановка ----------------------------------------------------

def _known(lib: ArtLibrary, ref: ArtRef) -> bool:
    return lib.has_part(ref.key, ref.value) if ref.kind == "part" else lib.has_color(ref.key, ref.value)


def _choices(lib: ArtLibrary, ref: ArtRef) -> list[str]:
    return list(lib.parts.get(ref.key, {}) if ref.kind == "part" else lib.palettes.get(ref.key, {}))


def _checked(lib: ArtLibrary, ref: ArtRef) -> bool:
    """Слоты, которых ещё нет в библиотеке (тайлсеты и иконки до этапа 2в), не проверяются."""
    return ref.key in (lib.parts if ref.kind == "part" else lib.palettes)


def check_art(game: s.Game, lib: ArtLibrary) -> list[Issue]:
    issues: list[Issue] = []
    for ref in iter_art_refs(game):
        if _checked(lib, ref) and not _known(lib, ref):
            what = f"деталь слота {ref.key}" if ref.kind == "part" else f"цвет из палитры {ref.key}"
            issues.append(Issue(path=ref.path, message=f"неизвестная {what}: '{ref.value}'. Допустимо: {', '.join(_choices(lib, ref))}"))

    for i, loc in enumerate(game.locations):
        bg = loc.background
        path = format_path("locations", i, "background")
        if bg.setting == "indoor" and bg.sky is not None:
            issues.append(Issue(path=format_path(path, "sky"), message="небо не рисуется в помещении (setting: indoor)", severity="warning"))
        tileset = lib.parts.get("tileset", {}).get(loc.theme)
        if tileset and tileset.setting and tileset.setting != bg.setting:
            issues.append(Issue(path=format_path("locations", i, "theme"), message=f"тайлсет '{loc.theme}' рассчитан на {tileset.setting}, а фон локации — {bg.setting}", severity="warning"))
        far = lib.parts.get("far", {}).get(bg.far)
        if far and far.setting and far.setting != bg.setting:
            issues.append(Issue(path=format_path(path, "far"), message=f"дальний план '{bg.far}' рассчитан на {far.setting}, а локация — {bg.setting}", severity="warning"))
    return issues


def repair_art(game: s.Game, lib: ArtLibrary) -> list[Issue]:
    """Последний шаг после неудачной автопочинки (§6.7): неизвестное → деталь или цвет по умолчанию."""
    warnings = []
    for ref in iter_art_refs(game):
        if not _checked(lib, ref) or _known(lib, ref):
            continue
        default = lib.default_part(ref.key) if ref.kind == "part" else lib.default_color(ref.key)
        ref.replace(default)
        warnings.append(Issue(path=ref.path, message=f"'{ref.value}' нет в библиотеке, подставлено '{default}'", severity="warning"))
    return warnings
