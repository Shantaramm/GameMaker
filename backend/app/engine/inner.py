"""Внутренние навыки и проверки в разговоре (SPEC §5.10) — эталон для frontend/src/engine/inner.ts.

Проверка: 2d6 + навык против сложности. Две шестёрки — всегда успех, две единицы — всегда провал.
Пассивная проверка — без броска: навык + 6 ≥ сложности.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from . import schema as s

DIFFICULTY_TARGET = {"trivial": 6, "easy": 8, "medium": 10, "challenging": 12, "formidable": 14, "legendary": 16}
DIFFICULTY_STEP = {k: i for i, k in enumerate(DIFFICULTY_TARGET)}  # trivial 0 … legendary 5
DIFFICULTY_NAME = {"trivial": "элементарно", "easy": "легко", "medium": "средне", "challenging": "сложно",
                   "formidable": "очень сложно", "legendary": "легендарно"}
PASSIVE_BONUS = 6
SKILL_CAP = 6               # предел навыка без вещей при прокачке
MOD_SKILL_CAP = 8           # предел с озарениями (mod_skill)
CHECK_XP_BASE = 5
CHECK_XP_STEP = 2
EXAMINE_XP = 3
SECRET_XP = 5               # найденный тайник (§5.12)
DEDUCE_XP = 10              # вывод на доске улик
QUEST_XP = 20
HEALTH_UNIT_SHARE = 6       # в игре с боями провал проверки отнимает 1/6 максимума HP


def check_target(difficulty: str) -> int:
    return DIFFICULTY_TARGET[difficulty]


def check_xp(difficulty: str) -> int:
    return CHECK_XP_BASE + CHECK_XP_STEP * DIFFICULTY_STEP[difficulty]


def chance(value: int, target: int) -> float:
    """Вероятность успеха 2d6 + value ≥ target с автоуспехом 6-6 и автопровалом 1-1."""
    ok = 0
    for a in range(1, 7):
        for b in range(1, 7):
            ok += _success(a, b, value, target)
    return ok / 36


def _success(a: int, b: int, value: int, target: int) -> bool:
    if a == 6 and b == 6:
        return True
    if a == 1 and b == 1:
        return False
    return a + b + value >= target


@dataclass
class Roll:
    dice: tuple[int, int]
    value: int
    target: int
    success: bool


def roll(value: int, target: int, rng: random.Random) -> Roll:
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    return Roll((a, b), value, target, _success(a, b, value, target))


def passive_heard(value: int, difficulty: str) -> bool:
    return value + PASSIVE_BONUS >= check_target(difficulty)


def check_key(dialogue_id: str, node_id: str, index: int) -> str:
    """Ключ проверки в состоянии: результат запоминается за конкретным вариантом конкретной реплики."""
    return f"{dialogue_id}:{node_id}:{index}"


def check_open(record: dict | None, check: s.SkillCheck, value: int) -> bool:
    """Можно ли выбрать вариант с проверкой. record — прошлый результат {"ok", "at"} или None."""
    if record is None or record["ok"]:
        return True
    return not check.red and value > record["at"]  # белая — снова, когда навык вырос


def health_unit(max_hp: int, no_combat: bool) -> int:
    return 1 if no_combat else max(1, round(max_hp / HEALTH_UNIT_SHARE))
