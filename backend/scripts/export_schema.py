"""Пишет schema/game.schema.json из Pydantic-моделей. Запуск: python scripts/export_schema.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.schema import game_json_schema  # noqa: E402

SCHEMA_PATH = ROOT / "schema" / "game.schema.json"


def render() -> str:
    return json.dumps(game_json_schema(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(ROOT)}")
