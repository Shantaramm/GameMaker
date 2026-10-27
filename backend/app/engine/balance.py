"""Детерминированный расчёт статов (SPEC §6.4). Все формулы и константы здесь."""

from __future__ import annotations

import math

from .schema import EffDamage, Game, Stats

HERO_STATS = Stats(hp=60, attack=9, defense=4, focus=6)

# tier → (hp, attack, defense)
ENEMY_TIER_STATS: dict[int, tuple[int, int, int]] = {
    1: (16, 7, 1),
    2: (22, 8, 2),
    3: (32, 10, 3),
    4: (44, 12, 5),
    5: (60, 14, 7),
}

# Кривая сложности: первая сцена ×EARLY, последняя ×LATE, между ними линейно.
DIFFICULTY_EARLY = 0.85
DIFFICULTY_LATE = 1.15

# Несколько врагов в одном бою слабее по отдельности. Атаку режем мягче, чем hp:
# иначе после вычета защиты героя слабые враги почти не наносят урона.
GROUP_HP_FACTOR = {1: 1.0, 2: 0.7, 3: 0.55}
GROUP_ATTACK_FACTOR = {1: 1.0, 2: 0.85, 3: 0.75}

# Урон способности врага ограничен ABILITY_DAMAGE_CAP × attack.
ABILITY_DAMAGE_CAP = 1.5

# Ослабление врагов в бою, который не проходит плейтест (§6.6).
TUNE_FACTOR = 0.85
TUNE_MAX_ITERATIONS = 6


def _enemy_contexts(game: Game) -> dict[str, tuple[int, int]]:
    """enemy_id → (индекс сцены первого появления, размер группы в этом бою)."""
    contexts: dict[str, tuple[int, int]] = {}
    for scene_index, scene in enumerate(game.scenes):
        for event in scene.events:
            if event.type != "battle":
                continue
            for enemy_id in event.enemies:
                contexts.setdefault(enemy_id, (scene_index, len(event.enemies)))
    return contexts


def apply_balance(game: Game) -> Game:
    """Выставляет стартовые статы героя и статы всех врагов. Меняет game на месте."""
    game.stats_template = HERO_STATS.model_copy()
    contexts = _enemy_contexts(game)
    last_scene = max(len(game.scenes) - 1, 1)

    for enemy in game.enemies:
        scene_index, group = contexts.get(enemy.id, (0, 1))
        curve = DIFFICULTY_EARLY + (DIFFICULTY_LATE - DIFFICULTY_EARLY) * scene_index / last_scene
        group = min(group, 3)
        hp, attack, defense = ENEMY_TIER_STATS[enemy.tier]

        enemy.hp = max(1, round(hp * curve * GROUP_HP_FACTOR[group]))
        enemy.attack = max(1, round(attack * curve * GROUP_ATTACK_FACTOR[group]))
        enemy.defense = round(defense * curve)

        cap = math.ceil(enemy.attack * ABILITY_DAMAGE_CAP)
        for ability in enemy.abilities:
            ability.effect = [
                EffDamage(damage=min(e.damage, cap)) if isinstance(e, EffDamage) else e
                for e in ability.effect
            ]
    return game


def weaken_enemies(game: Game, enemy_ids: set[str], factor: float = TUNE_FACTOR) -> None:
    for enemy in game.enemies:
        if enemy.id in enemy_ids and enemy.hp is not None:
            enemy.hp = max(1, math.floor(enemy.hp * factor))
            enemy.attack = max(1, math.floor(enemy.attack * factor))
            enemy.defense = math.floor(enemy.defense * factor)


def tune_until_winnable(game: Game, seed: int = 0):
    """Плейтест → ослабление врагов в непроходимых боях → повтор (§6.6).

    Возвращает последний отчёт плейтеста.
    """
    from .simulator import playtest

    report = playtest(game, seed=seed)
    for _ in range(TUNE_MAX_ITERATIONS):
        weak = [b for b in report.battles if b.fights and not b.ok]
        if not weak:
            break
        ids = {enemy_id for b in weak for enemy_id in b.enemies}
        weaken_enemies(game, ids)
        report = playtest(game, seed=seed)
    return report
