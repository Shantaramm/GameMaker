"""Шаги генерации, которые делает код, а не LLM: баланс (§6.5), сборка уровней (§6.6) и полей боя (§5.9)."""

from __future__ import annotations

from . import schema as s
from .arenas import build_arenas
from .balance import apply_balance
from .issues import Issue
from .levels import build_all


def prepare(game: s.Game) -> list[Issue]:
    """Выставляет числа, строит уровни и поля боя. Меняет game на месте; возвращает проблемы сборки уровней."""
    apply_balance(game)
    issues = build_all(game)
    game.arenas = build_arenas(game)
    return issues
