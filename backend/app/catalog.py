"""Каталог готовых игр: подборка (файлы в app/featured/) и игры, которые авторы опубликовали сами.

Подборку собирает scripts/build_featured.py; без публикации игра доступна только по ссылке.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FEATURED_DIR = Path(__file__).resolve().parent / "featured"
FEATURED = ["demo", "postman", "museum"]   # порядок карточек в подборке
COMMUNITY_LIMIT = 60


@lru_cache(maxsize=None)
def featured_game(game_id: str) -> dict[str, Any] | None:
    if game_id not in FEATURED:
        return None
    path = FEATURED_DIR / f"{game_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def card(game_id: str, game: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Что нужно карточке: название, логлайн, длительность, герой и компаньон, фон стартовой локации, главный враг."""
    meta = game["meta"]
    companion = next((c for c in game.get("characters", []) if c["role"] == "companion"), None)
    people = [game["hero"], *([companion] if companion else [])]
    start = next(loc for loc in game["locations"] if loc["id"] == game["start_location"])
    # обложка: герои на фоне стартовой локации лицом к самому сильному врагу игры
    boss = max(game.get("enemies", []), key=lambda e: e["tier"], default=None)
    return {
        "background": start["background"],
        "profile": game.get("profile", {"combat": "tactical", "dialogue": "rich"}),
        "enemy": {"id": boss["id"], "name": boss["name"], "appearance": boss["appearance"]} if boss else None,
        "id": game_id, "title": meta["title"], "logline": meta.get("logline", ""), "tone": meta.get("tone", ""),
        "est_minutes": meta.get("est_minutes"), "locations": len(game["locations"]), "endings": len(game["endings"]),
        "characters": [{"id": c["id"], "name": c["name"], "role": c["role"], "appearance": c["appearance"]} for c in people],
        **extra,
    }


def featured_cards() -> list[dict[str, Any]]:
    return [card(gid, g, featured=True) for gid in FEATURED if (g := featured_game(gid))]
