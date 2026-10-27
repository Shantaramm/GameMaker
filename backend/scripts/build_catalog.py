"""Собирает pixelart/catalog.md — список деталей и цветов для промптов (SPEC §5.7.5).

Запуск: python scripts/build_catalog.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.art import ArtLibrary, load_library  # noqa: E402

CATALOG_PATH = ROOT / "pixelart" / "catalog.md"

SECTIONS = [
    ("Портрет (PortraitSpec) — люди и человекоподобные", [
        ("head", "head", "форма лица"),
        ("hair", "hair", "причёска; `none` — лысый"),
        ("eyes", "eyes", "глаза (эмоции рантайм рисует сам)"),
        ("brows", "brows", "брови"),
        ("mouth", "mouth", "рот"),
        ("facial_hair", "facial_hair", "растительность на лице; поле можно не указывать"),
        ("outfit", "outfit", "одежда"),
        ("accessory", "accessory", "аксессуары, до 2 штук"),
    ]),
    ("Существо (CreatureSpec) — монстры и не-люди", [
        ("body", "creature_body", "тело"),
        ("features", "creature_feature", "особенности, до 3 штук"),
    ]),
    ("Фон сцены (BackgroundSpec)", [
        ("sky", "sky", "небо, только для `setting: outdoor`"),
        ("far", "far", "дальний план; в скобках — для какого setting"),
        ("props[].id", "prop", "предметы переднего плана, до 5 штук, `x` от 0 до 160"),
        ("ground", "ground", "земля или пол"),
    ]),
]

COLORS = [
    ("skin_tones", "`skin` — цвет кожи"),
    ("hair_colors", "`hair_color` — цвет волос (у капюшона `hood` не виден)"),
    ("eye_colors", "`eye_color` — цвет глаз"),
    ("cloth_colors", "`outfit_color`, `accent_color`, `bg_color`; у существ `color`, `accent_color`"),
]


def render(lib: ArtLibrary) -> str:
    lines = [
        "# Каталог пиксельных деталей",
        "",
        "Файл генерируется скриптом `backend/scripts/build_catalog.py` из `pixelart/library`. Не править руками.",
        "Выбирай id и цвета только из этого списка. У главных героев должны различаться причёска, цвет волос и наряд.",
        "",
    ]
    for title, fields in SECTIONS:
        lines += [f"## {title}", ""]
        for field, slot, note in fields:
            lines.append(f"### `{field}` — {note}")
            for part in lib.parts[slot].values():
                where = f" ({part.setting})" if part.setting and part.setting != "any" and slot in ("far", "prop") else ""
                lines.append(f"- `{part.id}` — {part.description}{where}")
            lines.append("")
    lines += [
        "`time`: `day` | `dusk` | `night`. `overlay`: `none` | `rain` | `fog` | `snow` | `dust`. "
        "`size` существа: `small` | `medium` | `large`.",
        "",
        "## Цвета",
        "",
    ]
    for group, note in COLORS:
        lines.append(f"- {note}: " + ", ".join(f"`{n}`" for n in lib.palettes[group]))
    lines += ["", "### `mood_palette` — общая гамма сцены"]
    for name, description in lib.palettes["mood_palettes"].items():
        lines.append(f"- `{name}` — {description}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    CATALOG_PATH.write_text(render(load_library()), encoding="utf-8")
    print(f"wrote {CATALOG_PATH.relative_to(ROOT)}")
