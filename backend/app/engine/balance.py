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

# tier → (hp, attack, defense). В тактическом бою (§5.9) отряд сильнее одиночного героя
# (компаньоны, фланги, кураж), поэтому HP ×1.5 и атака ×1.05 к версии 2: бой длится 4–6 раундов,
# а герой без компаньона, идущий напролом, проходит демо-игру, если играет с умом.
ENEMY_TIER_STATS: dict[int, tuple[int, int, int]] = {
    1: (24, 7, 1),
    2: (33, 8, 2),
    3: (48, 10, 3),
    4: (66, 13, 5),
    5: (90, 15, 7),
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

# Внутренние навыки (§5.10): значения героя и названия по умолчанию (если LLM не дала свои).
SKILL_BASE = 2
SKILL_STRONG = 4
SKILL_WEAK = 1
SKILL_EQUIP_CAP = 2
HEALTH_BASE = 3           # игра без боёв: Здоровье = 3 + Стойкость
MORALE_BASE = 3           # во всех играх: Дух = 3 + Воля
NO_COMBAT_HEAL_CAP = 2    # игра без боёв: лечение расходником — не больше 2 единиц Здоровья
DEFAULT_INNER_SKILLS = [
    s.InnerSkill(key="logic", name="Логика", description="Связывает факты, замечает противоречия."),
    s.InnerSkill(key="knowledge", name="Знания", description="Помнит книги, слухи и историю мира."),
    s.InnerSkill(key="empathy", name="Эмпатия", description="Чувствует, что человек скрывает за словами."),
    s.InnerSkill(key="will", name="Воля", description="Держит удар, не даёт сломаться. От неё зависит Дух."),
    s.InnerSkill(key="endurance", name="Стойкость", description="Выдерживает боль и холод. От неё зависит Здоровье."),
    s.InnerSkill(key="presence", name="Напор", description="Давит, убеждает силой, пугает."),
    s.InnerSkill(key="perception", name="Восприятие", description="Видит мелочи, слышит шорохи."),
    s.InnerSkill(key="finesse", name="Ловкость", description="Ловкие руки, тихие шаги, быстрая реакция."),
]

# Тактики в бою (§5.9): цена по tier в кураже или золоте.
TACTIC_POINTS_BY_TIER = {1: 2, 2: 4, 3: 6}
TACTIC_GOLD_BY_TIER = {1: 8, 2: 16, 3: 28}
# Базовые тактики есть в каждой игре; тактики игры их дополняют.
BASE_TACTICS = [
    s.Tactic(id="base_focus", name="Сосредоточиться", description="Атака бойца +3 до конца следующего хода врагов.",
             icon="dagger", tier=1, target="unit", effect=[s.EffModStat(mod_stat="attack", delta=3)], duration=1),
    s.Tactic(id="base_dash", name="Рывок", description="Боец пройдёт на 2 клетки дальше в этот ход.",
             icon="boots", tier=1, target="unit", move_bonus=2),
    s.Tactic(id="base_guard", name="Сомкнуть ряды", description="Защита всего отряда +2 до следующего хода.",
             icon="shield", tier=2, target="party", effect=[s.EffModStat(mod_stat="defense", delta=2)], duration=1),
    s.Tactic(id="base_second_wind", name="Второе дыхание", description="Боец восстанавливает 12 здоровья.",
             icon="herb", tier=2, target="unit", effect=[s.EffHeal(heal=12)]),
]


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
    apply_inner_skills(game)

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

    have = {t.id for t in game.tactics}
    if game.profile.combat != "none":
        game.tactics = [t.model_copy(deep=True) for t in BASE_TACTICS if t.id not in have] + game.tactics
    for tactic in game.tactics:
        table = TACTIC_POINTS_BY_TIER if tactic.currency == "points" else TACTIC_GOLD_BY_TIER
        tactic.cost = table[tactic.tier]

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
                skills={k: max(-SKILL_EQUIP_CAP, min(v, SKILL_EQUIP_CAP)) for k, v in b.skills.items() if v},
            )
        if game.profile.combat == "none" and item.kind == "consumable":
            item.effect = [s.EffHeal(heal=min(e.heal, NO_COMBAT_HEAL_CAP)) if isinstance(e, s.EffHeal) else e for e in item.effect]
    return game


def apply_inner_skills(game: s.Game) -> None:
    """Названия навыков (свои от LLM или по умолчанию), стартовые значения героя, Здоровье и Дух по профилю."""
    given = {sk.key: sk for sk in game.inner_skills}
    game.inner_skills = [given.get(d.key, d) for d in DEFAULT_INNER_SKILLS]
    strong = set(game.hero.strengths)
    game.hero_skills = {
        key: SKILL_STRONG if key in strong else SKILL_WEAK if key == game.hero.weakness else SKILL_BASE
        for key in s.SKILL_KEYS
    }
    game.stats_template.morale = MORALE_BASE + game.hero_skills["will"]
    if game.profile.combat == "none":
        # без боёв HP — это Здоровье из нескольких единиц; уровень даёт только очко навыка
        game.stats_template = s.Stats(hp=HEALTH_BASE + game.hero_skills["endurance"], attack=0, defense=0, focus=0,
                                      morale=game.stats_template.morale)
        game.progression.per_level = s.Stats(hp=0, attack=0, defense=0, focus=0)


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
