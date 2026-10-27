"""Headless-плейтест (SPEC §7.2) и эталонная реализация правил рантайма.

Правила здесь должны совпадать с frontend/src/engine (conditions.ts, battle.ts,
runtime.ts). Решения, которых нет в SPEC, перечислены в NOTES.md.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel, computed_field

from . import schema as s
from .issues import Issue, format_path

RUNS = 50
SEED = 1337
STEP_LIMIT = 2000
BATTLE_TURN_LIMIT = 100
MIN_BATTLE_WIN_RATE = 0.7
LOW_HP_RATIO = 0.3
FLEE_CHANCE = 0.5
DAMAGE_SPREAD = 0.2
FOCUS_REGEN_PER_TURN = 1


# --- Состояние и правила ---------------------------------------------------


@dataclass
class HeroState:
    hp: int
    max_hp: int
    attack: int
    defense: int
    focus: int
    max_focus: int
    inventory: Counter = field(default_factory=Counter)
    skills: set[str] = field(default_factory=set)
    flags: dict[str, bool] = field(default_factory=dict)

    def stat(self, name: str) -> int:
        return getattr(self, name)


def new_hero(game: s.Game) -> HeroState:
    if game.stats_template is None:
        raise ValueError("game is not balanced: stats_template is empty")
    t = game.stats_template
    return HeroState(
        hp=t.hp, max_hp=t.hp, attack=t.attack, defense=t.defense,
        focus=t.focus, max_focus=t.focus,
        inventory=Counter(game.start_items),
        skills=set(game.start_skills),
        flags={f.id: False for f in game.flags},
    )


def check(cond: s.Condition | None, hero: HeroState) -> bool:
    if cond is None:
        return True
    if isinstance(cond, s.CondAll):
        return all(check(c, hero) for c in cond.all)
    if isinstance(cond, s.CondAny):
        return any(check(c, hero) for c in cond.any)
    if isinstance(cond, s.CondNot):
        return not check(cond.not_, hero)
    if isinstance(cond, s.CondFlag):
        return hero.flags.get(cond.flag, False) == cond.is_
    if isinstance(cond, s.CondItem):
        return hero.inventory[cond.has_item] > 0
    if isinstance(cond, s.CondStat):
        value = hero.stat(cond.stat)
        return value >= cond.value if cond.op == ">=" else value <= cond.value
    raise TypeError(cond)


def apply_story_effects(effects: list[s.Effect], hero: HeroState) -> str | None:
    """Эффекты вне боя. Возвращает цель goto (остальные эффекты после него не выполняются)."""
    for e in effects:
        if isinstance(e, s.EffGoto):
            return e.goto
        apply_hero_effect(e, hero)
    return None


def apply_hero_effect(e: s.Effect, hero: HeroState) -> None:
    if isinstance(e, s.EffSetFlag):
        hero.flags[e.set_flag] = e.value
    elif isinstance(e, s.EffGiveItem):
        hero.inventory[e.give_item] += 1
    elif isinstance(e, s.EffTakeItem):
        if hero.inventory[e.take_item] > 0:
            hero.inventory[e.take_item] -= 1
    elif isinstance(e, s.EffLearnSkill):
        hero.skills.add(e.learn_skill)
    elif isinstance(e, s.EffHeal):
        hero.hp = min(hero.max_hp, hero.hp + e.heal)
    elif isinstance(e, s.EffDamage):
        hero.hp = max(1, hero.hp - e.damage)  # вне боя урон не убивает
    elif isinstance(e, s.EffModStat):
        if e.mod_stat == "hp":
            hero.max_hp = max(1, hero.max_hp + e.delta)
            hero.hp = max(1, min(hero.max_hp, hero.hp + e.delta))
        elif e.mod_stat == "focus":
            hero.max_focus = max(0, hero.max_focus + e.delta)
            hero.focus = max(0, min(hero.max_focus, hero.focus + e.delta))
        else:
            setattr(hero, e.mod_stat, max(0, hero.stat(e.mod_stat) + e.delta))


def roll_damage(attack: int, defense: int, rng: random.Random) -> int:
    base = max(1, attack - defense // 2)
    return max(1, round(base * rng.uniform(1 - DAMAGE_SPREAD, 1 + DAMAGE_SPREAD)))


# --- Бой --------------------------------------------------------------------


@dataclass
class Fighter:
    id: str
    hp: int
    attack: int
    defense: int
    abilities: list[s.EnemyAbility]
    turn: int = 0

    @property
    def alive(self) -> bool:
        return self.hp > 0


def _heal_amount(effects: list[s.Effect]) -> int:
    return sum(e.heal for e in effects if isinstance(e, s.EffHeal))


def _damage_amount(effects: list[s.Effect]) -> int:
    return sum(e.damage for e in effects if isinstance(e, s.EffDamage))


def run_battle(game: s.Game, battle: s.Battle, hero: HeroState, rng: random.Random) -> bool:
    """Бой бота: лечится при HP < 30%, иначе сильнейший доступный навык, иначе атака.

    HP героя переносится между боями, фокус в начале боя восполняется.
    Бафы навыков (mod_stat) действуют до конца боя.
    """
    enemies_by_id = {e.id: e for e in game.enemies}
    skills_by_id = {k.id: k for k in game.skills}
    items_by_id = {i.id: i for i in game.items}
    foes = [
        Fighter(e.id, e.hp, e.attack, e.defense, e.abilities)
        for e in (enemies_by_id[i] for i in battle.enemies)
    ]
    hero.focus = hero.max_focus
    buff = Counter()

    def hit(target: Fighter, effects: list[s.Effect]) -> None:
        for e in effects:
            if isinstance(e, s.EffDamage):
                target.hp -= e.damage
            elif isinstance(e, s.EffModStat) and e.mod_stat in ("attack", "defense"):
                setattr(target, e.mod_stat, max(0, getattr(target, e.mod_stat) + e.delta))

    for _ in range(BATTLE_TURN_LIMIT):
        target = min((f for f in foes if f.alive), key=lambda f: f.hp)
        known = [skills_by_id[k] for k in sorted(hero.skills) if k in skills_by_id]
        affordable = [k for k in known if k.cost_focus <= hero.focus]
        low_hp = hero.hp < hero.max_hp * LOW_HP_RATIO

        heal_items = [
            items_by_id[i] for i, n in sorted(hero.inventory.items())
            if n > 0 and i in items_by_id and items_by_id[i].consumable
            and _heal_amount(items_by_id[i].effect) > 0
        ]
        heal_skills = [k for k in affordable if k.target == "self" and _heal_amount(k.effect) > 0]
        attack_skills = [k for k in affordable if k.target == "enemy" and _damage_amount(k.effect) > 0]

        if low_hp and heal_items:
            item = max(heal_items, key=lambda i: _heal_amount(i.effect))
            hero.inventory[item.id] -= 1
            for e in item.effect:
                if isinstance(e, s.EffDamage):
                    target.hp -= e.damage
                else:
                    apply_hero_effect(e, hero)
        elif low_hp and heal_skills:
            skill = max(heal_skills, key=lambda k: _heal_amount(k.effect))
            hero.focus -= skill.cost_focus
            for e in skill.effect:
                if isinstance(e, s.EffModStat):
                    buff[e.mod_stat] += e.delta
                else:
                    apply_hero_effect(e, hero)
        elif attack_skills:
            skill = max(attack_skills, key=lambda k: _damage_amount(k.effect))
            hero.focus -= skill.cost_focus
            hit(target, skill.effect)
        else:
            target.hp -= roll_damage(hero.attack + buff["attack"], target.defense, rng)

        if not any(f.alive for f in foes):
            return True

        for foe in foes:
            if not foe.alive:
                continue
            foe.turn += 1
            ability = next((a for a in foe.abilities if foe.turn % a.every_n_turns == 0), None)
            if ability:
                for e in ability.effect:
                    if isinstance(e, s.EffDamage):
                        hero.hp -= e.damage
                    elif isinstance(e, s.EffHeal):
                        foe.hp += e.heal
                    elif isinstance(e, s.EffModStat) and e.mod_stat in ("attack", "defense"):
                        setattr(foe, e.mod_stat, max(0, getattr(foe, e.mod_stat) + e.delta))
            else:
                hero.hp -= roll_damage(foe.attack, hero.defense + buff["defense"], rng)
            if hero.hp <= 0:
                return False

        hero.focus = min(hero.max_focus, hero.focus + FOCUS_REGEN_PER_TURN)
    return False


# --- Прохождение ----------------------------------------------------------


class BattleStats(BaseModel):
    path: str
    scene_id: str
    event_id: str
    enemies: list[str]
    fights: int = 0
    wins: int = 0

    @computed_field
    @property
    def win_rate(self) -> float:
        return self.wins / self.fights if self.fights else 0.0

    @computed_field
    @property
    def ok(self) -> bool:
        return self.fights == 0 or self.win_rate >= MIN_BATTLE_WIN_RATE


class PlaytestReport(BaseModel):
    runs: int
    seed: int
    outcomes: dict[str, int]  # "ending:<id>" | "game_over" | "step_limit" | "dead_end"
    endings: dict[str, int]
    battles: list[BattleStats]
    issues: list[Issue]

    @computed_field
    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @computed_field
    @property
    def ending_rate(self) -> float:
        return sum(self.endings.values()) / self.runs if self.runs else 0.0


class _StepLimit(Exception):
    pass


def play_once(game: s.Game, rng: random.Random, battles: dict[tuple[int, int], BattleStats]) -> str:
    scene_index = {sc.id: i for i, sc in enumerate(game.scenes)}
    ending_ids = {e.id for e in game.endings}
    hero = new_hero(game)
    steps = 0

    def tick() -> None:
        nonlocal steps
        steps += 1
        if steps > STEP_LIMIT:
            raise _StepLimit

    def pick(options: list, cond_of) -> object | None:
        available = [o for o in options if check(cond_of(o), hero)]
        return rng.choice(available) if available else None

    current = game.start_scene
    try:
        while True:
            if current in ending_ids:
                return f"ending:{current}"
            si = scene_index[current]
            scene = game.scenes[si]
            jump: str | None = None

            for ei, event in enumerate(scene.events):
                tick()
                if isinstance(event, s.Narration):
                    continue
                if isinstance(event, s.Transition):
                    if check(event.condition, hero):
                        jump = event.to
                elif isinstance(event, s.Choice):
                    option = pick(event.options, lambda o: o.condition)
                    if option is None:
                        return "dead_end"
                    jump = apply_story_effects(option.effects, hero)
                elif isinstance(event, s.Dialogue):
                    nodes = {n.id: n for n in event.nodes}
                    node_id = event.start_node
                    while node_id != "end" and jump is None:
                        tick()
                        node = nodes[node_id]
                        if not node.choices:
                            node_id = node.next or "end"
                            continue
                        choice = pick(node.choices, lambda c: c.condition)
                        if choice is None:
                            return "dead_end"
                        jump = apply_story_effects(choice.effects, hero)
                        node_id = choice.next
                elif isinstance(event, s.Battle):
                    stats = battles[(si, ei)]
                    stats.fights += 1
                    if run_battle(game, event, hero, rng):
                        stats.wins += 1
                        jump = apply_story_effects(event.on_win, hero)
                    elif event.on_lose == "game_over":
                        return "game_over"
                    else:
                        hero.hp = 1
                        jump = apply_story_effects(event.on_lose, hero)
                if jump is not None:
                    break

            if jump is None:
                return "dead_end"
            current = jump
    except _StepLimit:
        return "step_limit"


def playtest(game: s.Game, runs: int = RUNS, seed: int = SEED) -> PlaytestReport:
    rng = random.Random(seed)
    battles: dict[tuple[int, int], BattleStats] = {}
    for si, scene in enumerate(game.scenes):
        for ei, event in enumerate(scene.events):
            if isinstance(event, s.Battle):
                battles[(si, ei)] = BattleStats(
                    path=format_path("scenes", si, "events", ei),
                    scene_id=scene.id, event_id=event.id, enemies=list(event.enemies),
                )

    outcomes = Counter(play_once(game, rng, battles) for _ in range(runs))
    endings = {k.split(":", 1)[1]: v for k, v in outcomes.items() if k.startswith("ending:")}

    issues: list[Issue] = []
    if not endings:
        issues.append(Issue(path="", message="ни одна концовка не достигнута в симуляциях"))
    if outcomes["step_limit"]:
        issues.append(Issue(path="", message=f"зацикливание: {outcomes['step_limit']} прохождений упёрлись в лимит {STEP_LIMIT} шагов"))
    if outcomes["dead_end"]:
        issues.append(Issue(path="", message=f"тупик: {outcomes['dead_end']} прохождений застряли без доступного выбора или goto"))
    for b in battles.values():
        if b.fights == 0:
            issues.append(Issue(path=b.path, message="бой ни разу не случился в симуляциях", severity="warning"))
        elif not b.ok:
            issues.append(Issue(path=b.path, message=f"бой выигран в {b.win_rate:.0%} симуляций, нужно ≥ {MIN_BATTLE_WIN_RATE:.0%}"))
    for ending in game.endings:
        if ending.id not in endings:
            issues.append(Issue(path=f"endings[{game.endings.index(ending)}]", message=f"концовка '{ending.id}' не достигнута в симуляциях", severity="warning"))

    return PlaytestReport(
        runs=runs, seed=seed, outcomes=dict(outcomes), endings=endings,
        battles=list(battles.values()), issues=issues,
    )
