"""Генерирует JSON-детали в pixelart/library из кода генераторов.

    python pixelart/tools/gen_library.py

JSON в library — источник для движка; генераторы — способ их нарисовать
и перерисовать. Править детали можно и руками в JSON, но тогда этот
скрипт их перезапишет.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import background  # noqa: E402
import creature  # noqa: E402
import icons  # noqa: E402
import portrait  # noqa: E402
import tiles  # noqa: E402
import walker  # noqa: E402

LIB = Path(__file__).resolve().parents[1] / "library"


def dump(parts: list[dict]) -> str:
    """Один объект на деталь, строки pixels — по одной на строку файла: удобно смотреть глазами."""
    def fmt(value, indent: int) -> str:
        pad = " " * indent
        if isinstance(value, dict) and "pixels" in value:
            inner = []
            for k, v in value.items():
                if k == "pixels":
                    rows = ",\n".join(f'{pad}    {json.dumps(r)}' for r in v)
                    inner.append(f'{pad}  "pixels": [\n{rows}\n{pad}  ]')
                else:
                    inner.append(f'{pad}  {json.dumps(k)}: {fmt(v, indent + 2)}')
            return "{\n" + ",\n".join(inner) + f"\n{pad}}}"
        if isinstance(value, dict):
            inner = [f'{pad}  {json.dumps(k)}: {fmt(v, indent + 2)}' for k, v in value.items()]
            return "{\n" + ",\n".join(inner) + f"\n{pad}}}"
        return json.dumps(value, ensure_ascii=False)

    return "[\n" + ",\n".join("  " + fmt(p, 2) for p in parts) + "\n]\n"


def write(group: str, slots: dict[str, list[dict]]) -> None:
    folder = LIB / group
    folder.mkdir(parents=True, exist_ok=True)
    for slot, parts in slots.items():
        (folder / f"{slot}.json").write_text(dump(parts), encoding="utf-8")
        print(f"{group}/{slot}.json: {len(parts)}")


def write_layout() -> None:
    layout = {
        "portrait": {"w": portrait.W, "h": portrait.H, "ref": list(portrait.REF), "emotions": portrait.EMOTIONS},
        "creature": {"w": creature.W, "h": creature.H, "ref": list(creature.REF)},
        "background": {"w": background.W, "h": background.H, "horizon": background.HORIZON,
                       "prop_base_y": background.PROP_BASE_Y},
        "tile": tiles.S,
        "walker": {"w": walker.W, "h": walker.H, "ref": list(walker.REF), "size": list(walker.SIZE),
                   "frames": {anim: len(poses) for anim, poses in walker.POSES.items()}},
    }
    (LIB / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_layout()
    write("portrait", portrait.build())
    write("creature", creature.build())
    write("background", background.build())
    write("walker", walker.build())
    write("tiles", tiles.build())
    write("icons", icons.build())
