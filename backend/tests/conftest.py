import copy
import json
from pathlib import Path

import pytest

DEMO_PATH = Path(__file__).parent / "fixtures" / "demo_game.json"
_DEMO = json.loads(DEMO_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def demo() -> dict:
    """Свежая копия демо-игры (сырой JSON), которую тест может ломать."""
    return copy.deepcopy(_DEMO)


def scene(game: dict, scene_id: str) -> dict:
    return next(sc for sc in game["scenes"] if sc["id"] == scene_id)


def event(game: dict, scene_id: str, event_id: str) -> dict:
    return next(e for e in scene(game, scene_id)["events"] if e.get("id") == event_id)
