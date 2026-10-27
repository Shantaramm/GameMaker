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


def location(game: dict, location_id: str) -> dict:
    return next(loc for loc in game["locations"] if loc["id"] == location_id)


def obj(game: dict, location_id: str, object_id: str) -> dict:
    return next(o for o in location(game, location_id)["objects"] if o["id"] == object_id)


def loc_index(game: dict, location_id: str) -> int:
    return next(i for i, loc in enumerate(game["locations"]) if loc["id"] == location_id)


def obj_path(game: dict, location_id: str, object_id: str) -> str:
    li = loc_index(game, location_id)
    oi = next(i for i, o in enumerate(game["locations"][li]["objects"]) if o["id"] == object_id)
    return f"locations[{li}].objects[{oi}]"
