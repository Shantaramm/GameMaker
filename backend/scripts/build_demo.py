"""Собирает демо-игру для фронта: фикстура → баланс → уровни → frontend/src/data/demo_game.json.

Фикстура tests/fixtures/demo_game.json — то, что отдал бы LLM; фронт получает
игру после шагов, которые делает код. Запуск: python scripts/build_demo.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.prepare import prepare  # noqa: E402
from app.engine.validator import validate  # noqa: E402

FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "demo_game.json"
OUT = ROOT / "frontend" / "src" / "data" / "demo_game.json"


def render() -> str:
    report = validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    if not report.ok:
        raise SystemExit("демо-игра не проходит валидатор:\n" + "\n".join(map(str, report.errors)))
    game = report.game
    problems = prepare(game)
    if problems:
        raise SystemExit("ошибки сборки уровней:\n" + "\n".join(map(str, problems)))
    return json.dumps(game.dump(), ensure_ascii=False, separators=(",", ":")) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
