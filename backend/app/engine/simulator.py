"""Headless-плейтест (SPEC §7.2) и эталонная реализация правил рантайма.

Правила здесь должны совпадать с frontend/src/engine (conditions.ts,
effects.ts, battle.ts, runtime.ts). Решения, которых нет в SPEC, — в NOTES.md.

Бот-исследователь в каждой локации обходит доступные объекты в случайном
порядке (говорит с NPC, торгует, дерётся, открывает сундуки, осматривает
предметы), затем уходит через случайный доступный выход, предпочитая
ещё не посещённые локации.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel, computed_field

from . import schema as s
from .issues import Issue, format_path
from . import inner
from .balance import HEALTH_BASE, MORALE_BASE
from .tactics import PARTY_MOVE, REST_HEAL, STYLE_RANGE, Battle, Unit, companion_stats, make_enemies, play_party_turn

RUNS = 50
SEED = 1337
STEP_LIMIT = 5000
MIN_BATTLE_WIN_RATE = 0.7
LOW_HP_RATIO = 0.3
UNVISITED_EXIT_WEIGHT = 3   # во сколько раз бот охотнее идёт в непосещённую локацию
ENDING_EXIT_WEIGHT = 0.3    # концовка без условий — не первое, что выбирает игрок, пока есть куда пойти
HEAL_STOCK = 2              # сколько лечебных предметов бот держит про запас
SLOTS = ("hand", "body", "trinket")


# --- Состояние и правила ---------------------------------------------------


@dataclass
class HeroState:
    """Базовые статы без экипировки; эффективные — через effective()."""

    hp: int
    max_hp: int
    attack: int
    defense: int
    focus: int
    max_focus: int
    gold: int = 0
    xp: int = 0
    level: int = 1
    inventory: Counter = field(default_factory=Counter)
    equipment: dict[str, str | None] = field(default_factory=lambda: dict.fromkeys(SLOTS))
    skills: set[str] = field(default_factory=set)
    flags: dict[str, bool] = field(default_factory=dict)
    defeated: set[str] = field(default_factory=set)
    opened: set[str] = field(default_factory=set)
    used: set[str] = field(default_factory=set)
    visited: set[str] = field(default_factory=set)
    # внутренние навыки (§5.10)
    morale: int = 0
    inner: dict[str, int] = field(default_factory=dict)
    skill_points: int = 0
    checks: dict[str, dict] = field(default_factory=dict)   # ключ проверки → {"ok": bool, "at": значение навыка}
    examined: set[str] = field(default_factory=set)
    quests_rewarded: set[str] = field(default_factory=set)
    revealed: set[str] = field(default_factory=set)        # найденные тайники (§5.12)


@dataclass
class Effective:
    attack: int
    defense: int
    max_hp: int
    max_focus: int
    max_morale: int = 0


class World:
    """Справочники игры, чтобы не искать по спискам на каждом шаге."""

    def __init__(self, game: s.Game) -> None:
        self.game = game
        self.items = {i.id: i for i in game.items}
        self.skills = {k.id: k for k in game.skills}
        self.enemies = {e.id: e for e in game.enemies}
        self.shops = {sh.id: sh for sh in game.shops}
        self.locations = {loc.id: loc for loc in game.locations}
        self.endings = {e.id for e in game.endings}
        self.no_combat = game.profile.combat == "none"

    def bonus(self, hero: HeroState) -> s.EquipBonus:
        total = s.EquipBonus()
        for item_id in hero.equipment.values():
            item = self.items.get(item_id or "")
            if item and item.equip:
                b = item.equip.bonus
                skills = dict(total.skills)
                for k, v in b.skills.items():
                    skills[k] = skills.get(k, 0) + v
                total = s.EquipBonus(attack=total.attack + b.attack, defense=total.defense + b.defense,
                                     focus=total.focus + b.focus, hp=total.hp + b.hp, skills=skills)
        return total

    def skill(self, hero: HeroState, key: str) -> int:
        """Внутренний навык с бонусами вещей."""
        return max(0, hero.inner.get(key, 0) + self.bonus(hero).skills.get(key, 0))

    def effective(self, hero: HeroState) -> Effective:
        b = self.bonus(hero)
        max_hp = HEALTH_BASE + self.skill(hero, "endurance") if self.no_combat else max(1, hero.max_hp + b.hp)
        return Effective(attack=max(0, hero.attack + b.attack), defense=max(0, hero.defense + b.defense),
                         max_hp=max(1, max_hp), max_focus=max(0, hero.max_focus + b.focus),
                         max_morale=MORALE_BASE + self.skill(hero, "will"))


def new_hero(game: s.Game) -> HeroState:
    if game.stats_template is None or game.progression is None:
        raise ValueError("game is not balanced: stats_template is empty")
    t = game.stats_template
    hero = HeroState(
        hp=t.hp, max_hp=t.hp, attack=t.attack, defense=t.defense,
        focus=t.focus, max_focus=t.focus, gold=game.start_gold or 0,
        inventory=Counter(game.start_items), skills=set(game.start_skills),
        flags={f.id: False for f in game.flags},
    )
    for slot, item_id in game.start_equipment.model_dump().items():
        if item_id:
            hero.inventory[item_id] += 1
            hero.equipment[slot] = item_id
    hero.inner = dict(game.hero_skills)
    eff = World(game).effective(hero)
    hero.hp = hero.max_hp = eff.max_hp if game.profile.combat == "none" else hero.hp
    hero.morale = eff.max_morale
    return hero


def check(cond: s.Condition | None, hero: HeroState, world: World) -> bool:
    if cond is None:
        return True
    if isinstance(cond, s.CondAll):
        return all(check(c, hero, world) for c in cond.all)
    if isinstance(cond, s.CondAny):
        return any(check(c, hero, world) for c in cond.any)
    if isinstance(cond, s.CondNot):
        return not check(cond.not_, hero, world)
    if isinstance(cond, s.CondFlag):
        return hero.flags.get(cond.flag, False) == cond.is_
    if isinstance(cond, s.CondItem):
        return hero.inventory[cond.has_item] > 0
    if isinstance(cond, s.CondDefeated):
        return cond.defeated in hero.defeated
    if isinstance(cond, s.CondSkill):
        value = world.skill(hero, cond.skill)
        return value >= cond.value if cond.op == ">=" else value <= cond.value
    if isinstance(cond, (s.CondStat, s.CondGold, s.CondLevel)):
        if isinstance(cond, s.CondStat):
            eff = world.effective(hero)
            value = {"hp": hero.hp, "focus": hero.focus, "attack": eff.attack, "defense": eff.defense,
                     "morale": hero.morale}[cond.stat]
            op = cond.op
        elif isinstance(cond, s.CondGold):
            value, op = hero.gold, cond.gold
        else:
            value, op = hero.level, cond.level
        return value >= cond.value if op == ">=" else value <= cond.value
    raise TypeError(cond)


def apply_story_effects(effects: list[s.Effect], hero: HeroState, world: World) -> str | None:
    """Эффекты вне боя. Возвращает цель goto (остальные эффекты после него не выполняются)."""
    for e in effects:
        if isinstance(e, s.EffGoto):
            return e.goto
        apply_hero_effect(e, hero, world)
    return None


def apply_hero_effect(e: s.Effect, hero: HeroState, world: World) -> None:
    eff = world.effective(hero)
    if isinstance(e, s.EffSetFlag):
        hero.flags[e.set_flag] = e.value
    elif isinstance(e, s.EffGiveItem):
        hero.inventory[e.give_item] += 1
        auto_equip(hero, world)
    elif isinstance(e, s.EffTakeItem):
        if hero.inventory[e.take_item] > 0:
            hero.inventory[e.take_item] -= 1
            if hero.inventory[e.take_item] == 0:
                for slot, item_id in hero.equipment.items():
                    if item_id == e.take_item:
                        hero.equipment[slot] = None
    elif isinstance(e, s.EffGiveGold):
        hero.gold += e.give_gold
    elif isinstance(e, s.EffTakeGold):
        hero.gold = max(0, hero.gold - e.take_gold)
    elif isinstance(e, s.EffLearnSkill):
        hero.skills.add(e.learn_skill)
    elif isinstance(e, s.EffHeal):
        hero.hp = min(eff.max_hp, hero.hp + e.heal)
    elif isinstance(e, s.EffDamage):
        hero.hp = max(1, hero.hp - e.damage)  # вне боя урон не убивает
    elif isinstance(e, s.EffModSkill):
        hero.inner[e.mod_skill] = max(0, min(inner.MOD_SKILL_CAP, hero.inner.get(e.mod_skill, 0) + e.delta))
        hero.morale = min(hero.morale, world.effective(hero).max_morale)
        hero.hp = min(hero.hp, world.effective(hero).max_hp)
    elif isinstance(e, s.EffModStat):
        if e.mod_stat == "morale":
            hero.morale = max(1, min(world.effective(hero).max_morale, hero.morale + e.delta))
        elif e.mod_stat == "hp":
            hero.max_hp = max(1, hero.max_hp + e.delta)
            hero.hp = max(1, min(world.effective(hero).max_hp, hero.hp + e.delta))
        elif e.mod_stat == "focus":
            hero.max_focus = max(0, hero.max_focus + e.delta)
            hero.focus = max(0, min(world.effective(hero).max_focus, hero.focus + e.delta))
        else:
            setattr(hero, e.mod_stat, max(0, getattr(hero, e.mod_stat) + e.delta))


def equip_score(item: s.Item) -> float:
    b = item.equip.bonus if item.equip else s.EquipBonus()
    return 2 * b.attack + 2 * b.defense + b.focus + b.hp / 5


def auto_equip(hero: HeroState, world: World) -> None:
    """Бот (и кнопка «надеть лучшее» в рантайме) носит в каждом слоте предмет с наибольшим бонусом."""
    for slot in SLOTS:
        options = [world.items[i] for i, n in hero.inventory.items()
                   if n > 0 and i in world.items and world.items[i].equip and world.items[i].equip.slot == slot]
        if options:
            hero.equipment[slot] = max(options, key=lambda it: (equip_score(it), it.id)).id
    eff = world.effective(hero)
    hero.hp = min(hero.hp, eff.max_hp)


def gain_xp(hero: HeroState, xp: int, game: s.Game, world: World) -> None:
    """Опыт и повышение уровня: прирост статов, очко навыка и полное восстановление HP, фокуса и Духа."""
    hero.xp += xp
    prog = game.progression
    while hero.level - 1 < len(prog.xp_to_level) and hero.xp >= prog.xp_to_level[hero.level - 1]:
        hero.level += 1
        p = prog.per_level
        hero.max_hp += p.hp
        hero.attack += p.attack
        hero.defense += p.defense
        hero.max_focus += p.focus
        hero.skill_points += 1
        eff = world.effective(hero)
        hero.hp, hero.focus, hero.morale = eff.max_hp, eff.max_focus, eff.max_morale


def spend_skill_points(hero: HeroState, game: s.Game) -> None:
    """Бот: очки — в сильные навыки (самый низкий из них), затем в самый низкий навык; предел SKILL_CAP."""
    while hero.skill_points > 0:
        order = [k for k in game.hero.strengths if hero.inner.get(k, 0) < inner.SKILL_CAP]
        if not order:
            order = sorted((k for k in s.SKILL_KEYS if hero.inner.get(k, 0) < inner.SKILL_CAP), key=lambda k: hero.inner.get(k, 0))
        if not order:
            return
        key = min(order, key=lambda k: hero.inner.get(k, 0))
        hero.inner[key] = hero.inner.get(key, 0) + 1
        hero.skill_points -= 1
        if key == "will":  # как spendSkillPoint в effects.ts: новый максимум Духа сразу доступен
            hero.morale += 1
        elif key == "endurance" and game.profile.combat == "none":
            hero.hp += 1


# --- Бой (тактический, §5.9; правила — tactics.py) -------------------------------


def _heal_amount(effects: list[s.Effect]) -> int:
    return sum(e.heal for e in effects if isinstance(e, s.EffHeal))


def party_units(hero: HeroState, world: World, arena: s.Arena) -> list[Unit]:
    """Герой (статы с экипировкой) и компаньоны, которые сейчас с ним (статы от базовых статов героя)."""
    eff = world.effective(hero)
    weapon = world.items.get(hero.equipment.get("hand") or "")
    x, y = arena.party[0]
    g = world.game
    units = [Unit(id="hero", name=g.hero.name, side="party", kind="hero", hp=hero.hp, max_hp=eff.max_hp,
                  attack=eff.attack, defense=eff.defense, focus=eff.max_focus, max_focus=eff.max_focus,
                  move=PARTY_MOVE, range=weapon.equip.range if weapon and weapon.equip else 1,
                  pos=(x, y), facing=(1, 0), skills=sorted(hero.skills))]
    for c in g.characters:
        if c.role != "companion" or not check(c.joins, hero, world) or len(units) >= len(arena.party):
            continue
        hp, atk, dfn, foc = companion_stats(hero.max_hp, hero.attack, hero.defense, hero.max_focus)
        combat = c.combat or s.CompanionCombat()
        x, y = arena.party[len(units)]
        units.append(Unit(id=c.id, name=c.name, side="party", kind="companion", hp=hp, max_hp=hp, attack=atk,
                          defense=dfn, focus=foc, max_focus=foc, move=PARTY_MOVE, range=STYLE_RANGE[combat.style],
                          pos=(x, y), facing=(1, 0), skills=list(combat.skills)))
    return units


def available_tactics(hero: HeroState, world: World) -> list[s.Tactic]:
    return [t for t in world.game.tactics if check(t.unlock, hero, world)]


def start_battle(foe: s.Foe, hero: HeroState, world: World, rng: random.Random) -> Battle:
    arena = world.game.arenas.get(foe.id)
    if arena is None:
        raise ValueError(f"нет поля боя для '{foe.id}': игра не подготовлена (prepare)")

    def wallet(delta: int | None) -> int:
        if delta is not None:
            hero.gold += delta
        return hero.gold

    return Battle(arena, party_units(hero, world, arena), make_enemies(foe, world.enemies, arena),
                  available_tactics(hero, world), foe.can_flee, rng, wallet)


def run_battle(foe: s.Foe, hero: HeroState, world: World, rng: random.Random) -> bool:
    """Бой бота (§7.2). HP героя переносится между боями (после победы +30% — передышка); фокус в начале боя полный."""
    b = start_battle(foe, hero, world, rng)

    def take(item_id: str) -> bool:
        if hero.inventory[item_id] <= 0:
            return False
        hero.inventory[item_id] -= 1
        return True

    while b.result is None:
        play_party_turn(b, world.skills, world.items, hero.inventory, take)
    hero.hp = max(0, b.hero().hp)
    if b.result == "win":
        hero.hp = min(b.hero().max_hp, hero.hp + round(b.hero().max_hp * REST_HEAL))
    return b.result == "win"


# --- Торговля ----------------------------------------------------------------


def shop_as_bot(shop: s.Shop, hero: HeroState, world: World) -> None:
    """Покупает экипировку лучше надетой, затем лечение про запас."""
    for item_id in sorted(shop.items, key=lambda i: -equip_score(world.items[i])):
        item = world.items[item_id]
        if item.kind != "equipment" or not item.equip or hero.inventory[item_id] > 0:
            continue
        current = world.items.get(hero.equipment[item.equip.slot] or "")
        if (current is None or equip_score(item) > equip_score(current)) and hero.gold >= (item.price or 0):
            hero.gold -= item.price or 0
            hero.inventory[item_id] += 1
    auto_equip(hero, world)
    heals = [world.items[i] for i in shop.items if world.items[i].kind == "consumable" and _heal_amount(world.items[i].effect) > 0]
    if heals:
        cheapest = min(heals, key=lambda it: (it.price or 0, it.id))
        while sum(hero.inventory[h.id] for h in heals) < HEAL_STOCK and hero.gold >= (cheapest.price or 0):
            hero.gold -= cheapest.price or 0
            hero.inventory[cheapest.id] += 1


# --- Прохождение ----------------------------------------------------------


class BattleStats(BaseModel):
    path: str
    location_id: str
    object_id: str
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
    quests_completed: dict[str, int]
    avg_final_level: float
    checks_attempted: int = 0   # проверки навыков за все прогоны (§5.10)
    checks_passed: int = 0
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


class _Over(Exception):
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome


@dataclass
class Run:
    game: s.Game
    world: World
    rng: random.Random
    battles: dict[str, BattleStats]
    hero: HeroState = field(init=False)
    steps: int = 0
    checks_stats: list[int] = field(default_factory=lambda: [0, 0])  # попыток, успехов

    def __post_init__(self) -> None:
        self.hero = new_hero(self.game)

    def tick(self) -> None:
        self.steps += 1
        if self.steps > STEP_LIMIT:
            raise _StepLimit

    def ok(self, cond: s.Condition | None) -> bool:
        return check(cond, self.hero, self.world)

    def run_event(self, event: s.Event) -> str | None:
        """Возвращает цель goto, если событие увело героя."""
        self.tick()
        if not self.ok(event.condition):
            return None
        if isinstance(event, s.Narration):
            return None
        if isinstance(event, s.Choice):
            options = [o for o in event.options if self.ok(o.condition)]
            if not options:
                raise _Over("dead_end")
            return apply_story_effects(self.rng.choice(options).effects, self.hero, self.world)
        nodes = {n.id: n for n in event.nodes}
        node_id = start_node(event, self.hero, self.world)
        while node_id != "end":
            self.tick()
            node = nodes[node_id]
            if not node.choices:
                node_id = node.next or "end"
                continue
            choices = [(i, c) for i, c in enumerate(node.choices) if self.ok(c.condition) and self.check_open(event.id, node.id, i, c)]
            if not choices:
                raise _Over("dead_end")
            index, choice = self.rng.choice(choices)
            jump = apply_story_effects(choice.effects, self.hero, self.world)
            if jump is not None:
                return jump
            node_id = choice.next if choice.check is None else self.resolve_check(event.id, node.id, index, choice)
        return None

    def check_open(self, dialogue_id: str, node_id: str, index: int, choice: s.DialogueChoice) -> bool:
        if choice.check is None:
            return True
        record = self.hero.checks.get(inner.check_key(dialogue_id, node_id, index))
        return inner.check_open(record, choice.check, self.world.skill(self.hero, choice.check.skill))

    def resolve_check(self, dialogue_id: str, node_id: str, index: int, choice: s.DialogueChoice) -> str:
        """Бросок 2d6 + навык; запоминает результат; при провале — урон Здоровью или Духу. Возвращает следующий узел."""
        h, chk = self.hero, choice.check
        key = inner.check_key(dialogue_id, node_id, index)
        if h.checks.get(key, {}).get("ok"):
            return choice.next  # уже пройдена — без броска
        value = self.world.skill(h, chk.skill)
        result = inner.roll(value, inner.check_target(chk.difficulty), self.rng)
        h.checks[key] = {"ok": result.success, "at": value}
        self.checks_stats[0] += 1
        if result.success:
            self.checks_stats[1] += 1
            self.reward(inner.check_xp(chk.difficulty))
            return choice.next
        if chk.damage == "health":
            h.hp -= inner.health_unit(self.world.effective(h).max_hp, self.world.no_combat)
        elif chk.damage == "morale":
            h.morale -= 1
        if h.hp <= 0 or h.morale <= 0:
            raise _Over("game_over")
        return chk.failure

    def reward(self, xp: int) -> None:
        gain_xp(self.hero, xp, self.game, self.world)
        spend_skill_points(self.hero, self.game)

    def reward_quests(self) -> None:
        for q in self.game.quests:
            if q.id not in self.hero.quests_rewarded and quest_done(q, self.hero, self.world):
                self.hero.quests_rewarded.add(q.id)
                self.reward(inner.QUEST_XP)

    def reveal(self, loc: s.Location) -> None:
        """Тайники локации, которые герой замечает сейчас: пассивная проверка, как revealSecrets в runtime.ts."""
        h = self.hero
        for obj in loc.objects:
            if obj.hidden and obj.id not in h.revealed and self.ok(obj.condition) \
                    and inner.passive_heard(self.world.skill(h, obj.hidden.skill), obj.hidden.difficulty):
                h.revealed.add(obj.id)
                self.reward(inner.SECRET_XP)

    def present(self, obj: s.MapObject) -> bool:
        h = self.hero
        if obj.hidden and obj.id not in h.revealed:
            return False
        if obj.id in h.defeated or obj.id in h.opened or (isinstance(obj, s.Thing) and obj.once and obj.id in h.used):
            return False
        return self.ok(obj.condition)

    def interact(self, obj: s.MapObject) -> str | None:
        self.tick()
        h = self.hero
        if isinstance(obj, s.Npc):
            jump = self.run_event(obj.dialogue)
            if jump is None and obj.shop:
                shop_as_bot(self.world.shops[obj.shop], h, self.world)
            return jump
        if isinstance(obj, s.Foe):
            stats = self.battles[obj.id]
            stats.fights += 1
            if run_battle(obj, h, self.world, self.rng):
                stats.wins += 1
                h.defeated.add(obj.id)
                enemies = [self.world.enemies[e] for e in obj.enemies]
                h.gold += sum(e.gold or 0 for e in enemies)
                self.reward(sum(e.xp or 0 for e in enemies))
                return apply_story_effects(obj.on_win, h, self.world)
            if obj.on_lose == "game_over":
                raise _Over("game_over")
            h.hp = 1
            return apply_story_effects(obj.on_lose, h, self.world)
        if isinstance(obj, s.Chest):
            if not self.ok(obj.requires):
                return None
            h.opened.add(obj.id)
            return apply_story_effects(obj.contents, h, self.world)
        if isinstance(obj, s.Thing):
            if obj.once:
                h.used.add(obj.id)
            if obj.id not in h.examined:
                h.examined.add(obj.id)
                self.reward(inner.EXAMINE_XP)
            return self.run_event(obj.event)
        return None

    def play(self) -> str:
        current = self.game.start_location
        try:
            while True:
                if current in self.world.endings:
                    return f"ending:{current}"
                current = self.visit(self.world.locations[current])
        except _StepLimit:
            return "step_limit"
        except _Over as over:
            return over.outcome

    def visit(self, loc: s.Location) -> str:
        """Одно посещение локации. Возвращает, куда герой ушёл."""
        h = self.hero
        if loc.id not in h.visited:
            h.visited.add(loc.id)
            for event in loc.on_enter:
                jump = self.run_event(event)
                if jump is not None:
                    return jump
        self.reveal(loc)
        objects = [o for o in loc.objects if not isinstance(o, s.Exit)]
        self.rng.shuffle(objects)
        for obj in objects:
            self.reveal(loc)  # навык мог вырасти после прошлого объекта
            if self.present(obj):
                jump = self.interact(obj)
                self.reward_quests()
                if jump is not None:
                    return jump
        exits = [o for o in loc.objects if isinstance(o, s.Exit) and self.present(o) and self.ok(o.requires)]
        if not exits:
            raise _Over("dead_end")
        weights = [ENDING_EXIT_WEIGHT if e.to in self.world.endings and e.requires is None
                   else UNVISITED_EXIT_WEIGHT if e.to not in h.visited else 1 for e in exits]
        return self.rng.choices(exits, weights=weights)[0].to


def start_node(dialogue: s.Dialogue, hero: HeroState, world: World) -> str:
    """Первая реплика: первая подходящая entries, иначе start_node (§5.10)."""
    for entry in dialogue.entries:
        if check(entry.condition, hero, world):
            return entry.node
    return dialogue.start_node


def quest_done(quest: s.Quest, hero: HeroState, world: World) -> bool:
    return all(check(st.done, hero, world) for st in quest.stages)


def playtest(game: s.Game, runs: int = RUNS, seed: int = SEED) -> PlaytestReport:
    rng = random.Random(seed)
    world = World(game)
    battles: dict[str, BattleStats] = {}
    for li, loc in enumerate(game.locations):
        for oi, obj in enumerate(loc.objects):
            if isinstance(obj, s.Foe):
                battles[obj.id] = BattleStats(
                    path=format_path("locations", li, "objects", oi),
                    location_id=loc.id, object_id=obj.id, enemies=list(obj.enemies),
                )

    outcomes: Counter = Counter()
    quests: Counter = Counter()
    levels: list[int] = []
    checks = [0, 0]
    for _ in range(runs):
        run = Run(game, world, rng, battles)
        outcome = run.play()
        outcomes[outcome] += 1
        checks[0] += run.checks_stats[0]
        checks[1] += run.checks_stats[1]
        if outcome.startswith("ending:"):
            levels.append(run.hero.level)
            for q in game.quests:
                if quest_done(q, run.hero, world):
                    quests[q.id] += 1
    endings = {k.split(":", 1)[1]: v for k, v in outcomes.items() if k.startswith("ending:")}

    issues: list[Issue] = []
    if not endings:
        issues.append(Issue(path="", message="ни одна концовка не достигнута в симуляциях"))
    if outcomes["step_limit"]:
        issues.append(Issue(path="", message=f"зацикливание: {outcomes['step_limit']} прохождений упёрлись в лимит {STEP_LIMIT} шагов"))
    if outcomes["dead_end"]:
        issues.append(Issue(path="", message=f"тупик: {outcomes['dead_end']} прохождений застряли без доступного выхода или выбора"))
    for b in battles.values():
        if b.fights == 0:
            issues.append(Issue(path=b.path, message="бой ни разу не случился в симуляциях", severity="warning"))
        elif not b.ok:
            issues.append(Issue(path=b.path, message=f"бой выигран в {b.win_rate:.0%} встреч, нужно ≥ {MIN_BATTLE_WIN_RATE:.0%}"))
    for i, ending in enumerate(game.endings):
        if ending.id not in endings:
            issues.append(Issue(path=format_path("endings", i), message=f"концовка '{ending.id}' не достигнута в симуляциях", severity="warning"))
    for i, q in enumerate(game.quests):
        if not quests[q.id]:
            severity = "error" if q.main else "warning"
            kind = "основной" if q.main else "побочный"
            issues.append(Issue(path=format_path("quests", i), message=f"{kind} квест '{q.id}' ни разу не выполнен к концовке", severity=severity))

    return PlaytestReport(
        runs=runs, seed=seed, outcomes=dict(outcomes), endings=endings,
        battles=list(battles.values()), quests_completed=dict(quests),
        avg_final_level=round(sum(levels) / len(levels), 2) if levels else 0.0,
        checks_attempted=checks[0], checks_passed=checks[1],
        issues=issues,
    )
