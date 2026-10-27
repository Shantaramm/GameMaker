"""Игры подборки → backend/app/featured/*.json (проверяет test_featured_in_sync).

demo — демо-игра из фикстуры; postman и museum — игры, написанные через ретранслятор
(записанные ответы в tests/fixtures/relay_*/ проходят через настоящий пайплайн).
museum — игра без боёв с глубокими диалогами (профиль combat: none, dialogue: deep).
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import FEATURED_DIR  # noqa: E402
from app.engine.prepare import prepare  # noqa: E402
from app.engine.validator import validate  # noqa: E402
from app.generation.pipeline import Pipeline  # noqa: E402
from app.llm import ScriptedLLM  # noqa: E402

TESTS = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def demo() -> dict:
    game = validate(json.loads((TESTS / "demo_game.json").read_text(encoding="utf-8"))).game
    prepare(game)
    return game.dump()


def from_relay(name: str, game_id: str) -> dict:
    """Записанные ответы оператора (ретранслятор) — через настоящий пайплайн."""
    relay = TESTS / name
    llm = ScriptedLLM(lambda step, _: (relay / f"{step.replace(':', '_')}.json").read_text(encoding="utf-8"))
    brief = (relay / "brief.md").read_text(encoding="utf-8")
    return asyncio.run(Pipeline(llm, brief, game_id).run()).game.dump()


def build() -> dict[str, dict]:
    return {"demo": demo(), "postman": from_relay("relay_postman", "postman"), "museum": from_relay("relay_museum", "museum")}


def dumps(game: dict) -> str:
    return json.dumps(game, ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    FEATURED_DIR.mkdir(exist_ok=True)
    for name, game in build().items():
        (FEATURED_DIR / f"{name}.json").write_text(dumps(game), encoding="utf-8")
        print(f"wrote backend/app/featured/{name}.json")
