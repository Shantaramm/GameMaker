"""Детерминированный расчёт чисел (SPEC §6.5). Все формулы и константы здесь.

LLM задаёт только tier врагов и value_tier предметов; статы, опыт, золото,
цены и пределы экипировки считает этот модуль.
"""

from __future__ import annotations

import math

from . import schema as s
from .world import location_depth

HERO_STATS = s.Stats(hp=60, attack=9, defense=4, focus=6)
START_GOLD = 15

# tier → (hp, attack, defense)
ENEMY_TIER_STATS: dict[int, tuple[int, int, int]] = {
    1: (16, 7, 1),
    2: (22, 8, 2),
    3: (32, 10, 3),
    4: (44, 12, 5),
    5: (60, 14, 7),
}
XP_BY_TIER = {1: 12, 2: 20, 3: 32, 4: 48, 5: 70}
GOLD_BY_TIER = {1: 6, 2: 10, 3: 16, 4: 24, 5: 34}

# Кривая сложности по глубине локации: стартовая ×EARLY, самая дальняя ×LATE.
DIFFICULTY_EARLY = 0.85
DIFFICULTY_LATE = 1.2

# Несколько врагов в одном бою слабее по отдельности. Атаку режем мягче, чем hp:
# иначе после вычета защиты героя слабые враги почти не наносят урона.
GROUP_HP_FACTOR = {1: 1.0, 2: 0.7, 3: 0.55}
GROUP_ATTACK_FACTOR = {1: 1.0, 2: 0.85, 3: 0.75}

# Урон способности врага ограничен ABILITY_DAMAGE_CAP × attack.
ABILITY_DAMAGE_CAP = 1.5

# Уровни: суммарный опыт для уровней 2, 3, … и прирост статов за уровень.
PROGRESSION = s.Progression(
    xp_to_level=[25, 60, 110, 180, 270, 380],
    per_level=s.Stats(hp=8, attack=2, defense=1, focus=1),
)

PRICE_BY_TIER = {1: 10, 2: 22, 3: 40, 4: 65, 5: 100}
SELL_RATE = 0.5


def equip_cap(tier: int) -> s.EquipBonus:
    """Максимальный бонус экипировки ценности tier по каждому стату."""
    return s.EquipBonus(attack=tier + 1, defense=tier + 1, focus=tier, hp=5 * tier)


# Ослабление врагов в бою, который не проходит плейтест (§6.8).
TUNE_FACTOR = 0.85
TUNE_MAX_ITERATIONS = 6


def sell_price(item: s.Item) -> int:
    return math.floor((item.price or 0) * SELL_RATE)


def _enemy_contexts(game: s.Game) -> dict[str, tuple[int, int]]:
    """enemy_id → (глубина локации первого появления, размер группы в этом бою)."""
    depth = location_depth(game)
    contexts: dict[str, tuple[int, int]] = {}
    for loc in sorted(game.locations, key=lambda l: depth[l.id]):
        for obj in loc.objects:
            if isinstance(obj, s.Foe):
                for enemy_id in obj.enemies:
                    contexts.setdefault(enemy_id, (depth[loc.id], len(obj.enemies)))
    return contexts


def apply_balance(game: s.Game) -> s.Game:
    """Выставляет все числа. Меняет game на месте и возвращает его."""
    game.stats_template = HERO_STATS.model_copy()
    game.progression = PROGRESSION.model_copy(deep=True)
    game.start_gold = START_GOLD

    contexts = _enemy_contexts(game)
    max_depth = max((d for d, _ in contexts.values()), default=0) or 1
    for enemy in game.enemies:
        depth, group = contexts.get(enemy.id, (0, 1))
        curve = DIFFICULTY_EARLY + (DIFFICULTY_LATE - DIFFICULTY_EARLY) * min(depth, max_depth) / max_depth
        group = min(group, 3)
        hp, attack, defense = ENEMY_TIER_STATS[enemy.tier]
        enemy.hp = max(1, round(hp * curve * GROUP_HP_FACTOR[group]))
        enemy.attack = max(1, round(attack * curve * GROUP_ATTACK_FACTOR[group]))
        enemy.defense = round(defense * curve)
        enemy.xp = XP_BY_TIER[enemy.tier]
        enemy.gold = GOLD_BY_TIER[enemy.tier]
        cap = math.ceil(enemy.attack * ABILITY_DAMAGE_CAP)
        for ability in enemy.abilities:
            ability.effect = [
                s.EffDamage(damage=min(e.damage, cap)) if isinstance(e, s.EffDamage) else e
                for e in ability.effect
            ]

    for item in game.items:
        item.price = PRICE_BY_TIER[item.value_tier]
        if item.equip:
            cap = equip_cap(item.value_tier)
            b = item.equip.bonus
            item.equip.bonus = s.EquipBonus(
                attack=max(-cap.attack, min(b.attack, cap.attack)),
                defense=max(-cap.defense, min(b.defense, cap.defense)),
                focus=max(-cap.focus, min(b.focus, cap.focus)),
                hp=max(-cap.hp, min(b.hp, cap.hp)),
            )
    return game


def weaken_enemies(game: s.Game, enemy_ids: set[str], factor: float = TUNE_FACTOR) -> None:
    for enemy in game.enemies:
        if enemy.id in enemy_ids and enemy.hp is not None:
            enemy.hp = max(1, math.floor(enemy.hp * factor))
            enemy.attack = max(1, math.floor(enemy.attack * factor))
            enemy.defense = math.floor(enemy.defense * factor)


def tune_until_winnable(game: s.Game, seed: int | None = None):
    """Плейтест → ослабление врагов в непроходимых боях → повтор (§6.8). Возвращает последний отчёт."""
    from .simulator import SEED, playtest

    seed = SEED if seed is None else seed
    report = playtest(game, seed=seed)
    for _ in range(TUNE_MAX_ITERATIONS):
        weak = [b for b in report.battles if b.fights and not b.ok]
        if not weak:
            break
        weaken_enemies(game, {enemy_id for b in weak for enemy_id in b.enemies})
        report = playtest(game, seed=seed)
    return report
