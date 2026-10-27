"""Шаги генерации, которые делает код, а не LLM: баланс (§6.5) и сборка уровней (§6.6)."""

from __future__ import annotations

from . import schema as s
from .balance import apply_balance
from .issues import Issue
from .levels import build_all


def prepare(game: s.Game) -> list[Issue]:
    """Выставляет числа и строит уровни. Меняет game на месте; возвращает проблемы сборки уровней."""
    apply_balance(game)
    return build_all(game)
