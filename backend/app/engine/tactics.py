"""Тактический бой на изометрическом поле (SPEC §5.9) — эталон правил для рантайма.

Правила и ИИ врагов должны совпадать с frontend/src/engine/tactics.ts. Бот отряда
(play_party_turn) — только для плейтеста; в рантайме за отряд ходит игрок.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from . import schema as s
from .arenas import NEIGHBOURS

PARTY_MOVE = 3
MOVE_BY_SIZE = {"small": 4, "medium": 3, "large": 2}
STYLE_RANGE = {"melee": 1, "support": 2, "ranged": 3}
SKILL_RANGE = 3              # навыки и предметы с уроном
ABILITY_RANGE = 3            # урон способности врага — на max(дальность, 3)
SKILL_BUFF_PHASES = 2        # сколько фаз отряда держится mod_stat навыка или предмета
MAX_ROUNDS = 30
MAX_POINTS = 12
FLANK_BONUS = 0.25
BACK_BONUS = 0.5
HIGH_BONUS = 0.2
KNOWN_WEAK_BONUS = 0.25     # слабость врага известна (§5.12)
BANE_BONUS = 0.5            # оружие или бомба против этой слабости
COMPANION_HP = 0.7
COMPANION_ATTACK = 0.8
FLEE_CHANCE = 0.5
DAMAGE_SPREAD = 0.2
FOCUS_REGEN = 1
LOW_HP_RATIO = 0.3
REST_HEAL = 0.3              # после победы герой восстанавливает долю максимума HP
FAR = 1000

Cell = tuple[int, int]


def roll_damage(attack: int, defense: int, rng: random.Random) -> int:
    base = max(1, attack - defense // 2)
    return max(1, round(base * rng.uniform(1 - DAMAGE_SPREAD, 1 + DAMAGE_SPREAD)))


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def sign(v: int) -> int:
    return (v > 0) - (v < 0)


def face_towards(src: Cell, dst: Cell) -> Cell:
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    return (sign(dx), 0) if abs(dx) >= abs(dy) else (0, sign(dy))


@dataclass
class Buff:
    stat: str      # attack | defense
    delta: int
    phases: int    # сколько ещё фаз своей стороны держится


@dataclass
class Unit:
    id: str
    name: str
    side: str      # party | enemy
    kind: str      # hero | companion | enemy
    hp: int
    max_hp: int
    attack: int
    defense: int
    focus: int
    max_focus: int
    move: int
    range: int
    pos: Cell
    facing: Cell
    abilities: list[s.EnemyAbility] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    buffs: list[Buff] = field(default_factory=list)
    turn: int = 0
    moved: bool = False
    acted: bool = False
    tactic_used: bool = False
    move_bonus: int = 0
    bane: str | None = None      # отряд: против какой слабости оружие (§5.12)
    weak: str | None = None      # враг: его слабость
    weak_known: bool = False     # враг: слабость в бестиарии

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def stat(self, name: str) -> int:
        return max(0, getattr(self, name) + sum(b.delta for b in self.buffs if b.stat == name))


class Field:
    def __init__(self, arena: s.Arena) -> None:
        self.w, self.h = arena.width, arena.height
        self.heights = [[0 if c == "#" else int(c) for c in row] for row in arena.cells]
        self.blocked = {(x, y) for y, row in enumerate(arena.cells) for x, c in enumerate(row) if c == "#"}

    def height(self, c: Cell) -> int:
        return self.heights[c[1]][c[0]]

    def step_ok(self, a: Cell, b: Cell) -> bool:
        x, y = b
        return 0 <= x < self.w and 0 <= y < self.h and b not in self.blocked and abs(self.height(a) - self.height(b)) <= 1

    def reachable(self, start: Cell, steps: int, occupied: set[Cell]) -> dict[Cell, tuple[int, Cell | None]]:
        """Клетка → (шагов, откуда пришли). Сквозь бойцов не пройти; порядок соседей фиксирован."""
        out: dict[Cell, tuple[int, Cell | None]] = {start: (0, None)}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            d = out[cur][0]
            if d == steps:
                continue
            for dx, dy in NEIGHBOURS:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt not in out and nxt not in occupied and self.step_ok(cur, nxt):
                    out[nxt] = (d + 1, cur)
                    queue.append(nxt)
        return out

    def path_dist(self, a: Cell, b: Cell) -> int | None:
        """Длина пути по рельефу без учёта бойцов (b достижима, даже если занята)."""
        if a == b:
            return 0
        seen = {a: 0}
        queue = deque([a])
        while queue:
            cur = queue.popleft()
            for dx, dy in NEIGHBOURS:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt not in seen and self.step_ok(cur, nxt):
                    seen[nxt] = seen[cur] + 1
                    if nxt == b:
                        return seen[nxt]
                    queue.append(nxt)
        return None


def direction(attacker: Cell, defender: Unit) -> str:
    vx, vy = attacker[0] - defender.pos[0], attacker[1] - defender.pos[1]
    dot = vx * defender.facing[0] + vy * defender.facing[1]
    return "front" if dot > 0 else "flank" if dot == 0 else "back"


DIRECTION_RANK = {"back": 0, "flank": 1, "front": 2}


@dataclass
class Event:
    actor: str
    target: str | None
    amount: int
    text: str
    kind: str = "hit"   # hit | heal | buff | move | info


class Battle:
    def __init__(self, arena: s.Arena, party: list[Unit], enemies: list[Unit], tactics: list[s.Tactic],
                 can_flee: bool, rng: random.Random, wallet: Callable[[int | None], int]) -> None:
        """wallet(delta) меняет золото героя на delta и возвращает остаток; wallet(None) — только остаток."""
        self.field = Field(arena)
        self.party = party
        self.enemies = enemies
        self.tactics = tactics
        self.can_flee = can_flee
        self.rng = rng
        self.wallet = wallet
        self.points = 0
        self.round = 1
        self.result: str | None = None   # win | lose | fled
        self.gold_used: set[str] = set()
        self.log: list[Event] = []

    # --- справочное ---

    @property
    def units(self) -> list[Unit]:
        return [u for u in self.party + self.enemies if u.alive]

    def occupied(self, except_unit: Unit | None = None) -> set[Cell]:
        return {u.pos for u in self.units if u is not except_unit}

    def moves(self, unit: Unit) -> dict[Cell, tuple[int, Cell | None]]:
        if unit.moved or unit.acted:
            return {unit.pos: (0, None)}
        return self.field.reachable(unit.pos, unit.move + unit.move_bonus, self.occupied(unit))

    def alive_enemies(self) -> list[Unit]:
        return [u for u in self.enemies if u.alive]

    def alive_party(self) -> list[Unit]:
        return [u for u in self.party if u.alive]

    def hero(self) -> Unit:
        return next(u for u in self.party if u.kind == "hero")

    # --- урон ---

    def strike(self, attacker: Unit, defender: Unit, base: int) -> tuple[int, str, bool]:
        side = direction(attacker.pos, defender)
        high = self.field.height(attacker.pos) > self.field.height(defender.pos)
        mult = 1 + (BACK_BONUS if side == "back" else FLANK_BONUS if side == "flank" else 0) + (HIGH_BONUS if high else 0)
        mult += weak_bonus(attacker, defender)
        return max(1, math.floor(base * mult + 0.5)), side, high

    def hurt(self, attacker: Unit, defender: Unit, dmg: int, label: str, side: str = "front", high: bool = False) -> None:
        defender.hp -= dmg
        note = {"flank": " (фланг)", "back": " (в спину)"}.get(side, "") + (" (сверху)" if high else "")
        self.log.append(Event(attacker.id, defender.id, dmg, f"{label}: {defender.name} −{dmg}{note}"))
        if attacker.side == "party":
            self.gain(1 + (side != "front") + high)
        if defender.alive:
            return
        if defender.side == "enemy":
            self.log.append(Event(attacker.id, defender.id, 0, f"{defender.name} повержен", "info"))
            if attacker.side == "party":
                self.gain(2)
            if not self.alive_enemies():
                self.result = "win"
        elif defender.kind == "hero":
            defender.hp = 0
            self.result = "lose"
        else:
            self.log.append(Event(attacker.id, defender.id, 0, f"{defender.name} выбывает из боя", "info"))

    def gain(self, n: int) -> None:
        self.points = min(MAX_POINTS, self.points + n)

    def apply_self(self, unit: Unit, e: s.Effect, phases: int, label: str) -> None:
        if isinstance(e, s.EffHeal):
            before = unit.hp
            unit.hp = min(unit.max_hp, unit.hp + e.heal)
            self.log.append(Event(unit.id, unit.id, before - unit.hp, f"{label}: {unit.name} +{unit.hp - before}", "heal"))
        elif isinstance(e, s.EffModStat) and e.mod_stat in ("attack", "defense"):
            unit.buffs.append(Buff(e.mod_stat, e.delta, phases))
            name = "атака" if e.mod_stat == "attack" else "защита"
            self.log.append(Event(unit.id, unit.id, 0, f"{label}: {unit.name} {name} {e.delta:+d}", "buff"))
        elif isinstance(e, s.EffModStat) and e.mod_stat == "hp" and e.delta > 0:
            self.apply_self(unit, s.EffHeal(heal=e.delta), phases, label)
        elif isinstance(e, s.EffModStat) and e.mod_stat == "focus":
            unit.focus = max(0, min(unit.max_focus, unit.focus + e.delta))

    # --- действия отряда ---

    def can_act(self, unit: Unit) -> bool:
        return self.result is None and unit.side == "party" and unit.alive and not unit.acted

    def move(self, unit: Unit, cell: Cell) -> bool:
        if not self.can_act(unit) or unit.moved:
            return False
        reach = self.moves(unit)
        if cell not in reach or cell == unit.pos:
            return False
        self._walk(unit, cell, reach)
        unit.moved = True
        return True

    def _walk(self, unit: Unit, cell: Cell, reach: dict[Cell, tuple[int, Cell | None]]) -> None:
        prev = reach[cell][1]
        if prev is not None:
            unit.facing = (cell[0] - prev[0], cell[1] - prev[1])
        unit.pos = cell

    def targets_in(self, unit: Unit, rng_: int) -> list[Unit]:
        foes = self.alive_enemies() if unit.side == "party" else self.alive_party()
        return [f for f in foes if manhattan(unit.pos, f.pos) <= rng_]

    def attack(self, unit: Unit, target: Unit) -> bool:
        if not self.can_act(unit) or not target.alive or manhattan(unit.pos, target.pos) > unit.range:
            return False
        unit.facing = face_towards(unit.pos, target.pos)
        dmg, side, high = self.strike(unit, target, roll_damage(unit.stat("attack"), target.stat("defense"), self.rng))
        self.hurt(unit, target, dmg, "Удар", side, high)
        unit.acted = True
        return True

    def skill(self, unit: Unit, skill: s.Skill, target: Unit | None) -> bool:
        if not self.can_act(unit) or skill.id not in unit.skills or unit.focus < skill.cost_focus:
            return False
        if skill.target == "enemy" and (target is None or not target.alive or manhattan(unit.pos, target.pos) > SKILL_RANGE):
            return False
        unit.focus -= skill.cost_focus
        for e in skill.effect:
            if skill.target == "enemy" and isinstance(e, s.EffDamage):
                unit.facing = face_towards(unit.pos, target.pos)
                dmg, side, high = self.strike(unit, target, e.damage)
                self.hurt(unit, target, dmg, skill.name, side, high)
            elif skill.target == "enemy" and isinstance(e, s.EffModStat) and e.mod_stat in ("attack", "defense"):
                target.buffs.append(Buff(e.mod_stat, e.delta, SKILL_BUFF_PHASES))
                self.log.append(Event(unit.id, target.id, 0, f"{skill.name}: {target.name} {e.delta:+d}", "buff"))
            elif skill.target == "self":
                self.apply_self(unit, e, SKILL_BUFF_PHASES, skill.name)
        unit.acted = True
        return True

    def item(self, unit: Unit, item: s.Item, target: Unit | None, take: Callable[[str], bool]) -> bool:
        """take(item_id) списывает предмет из сумки героя."""
        if not self.can_act(unit) or item.kind != "consumable":
            return False
        hits = [e for e in item.effect if isinstance(e, s.EffDamage)]
        if hits and (target is None or not target.alive or manhattan(unit.pos, target.pos) > SKILL_RANGE):
            return False
        if not take(item.id):
            return False
        for e in item.effect:
            if isinstance(e, s.EffDamage):
                dmg = math.floor(e.damage * (1 + weak_bonus(unit, target, item.bane)) + 0.5)
                self.hurt(unit, target, dmg, item.name)
            else:
                self.apply_self(unit, e, SKILL_BUFF_PHASES, item.name)
        unit.acted = True
        return True

    def defend(self, unit: Unit) -> bool:
        if not self.can_act(unit):
            return False
        delta = max(2, unit.defense // 2)
        unit.buffs.append(Buff("defense", delta, 1))
        self.log.append(Event(unit.id, unit.id, 0, f"{unit.name} в защите: защита +{delta}", "buff"))
        unit.acted = True
        return True

    def flee(self, unit: Unit) -> bool:
        if not self.can_act(unit) or unit.kind != "hero":
            return False
        unit.acted = True
        if self.can_flee and self.rng.random() < FLEE_CHANCE:
            self.result = "fled"
            self.log.append(Event(unit.id, None, 0, "Удалось сбежать!", "info"))
        else:
            self.log.append(Event(unit.id, None, 0, "Сбежать не вышло." if self.can_flee else "Отсюда не сбежать.", "info"))
        return True

    def tactic_ok(self, unit: Unit, tactic: s.Tactic) -> bool:
        if self.result is not None or unit.side != "party" or not unit.alive or unit.tactic_used or unit.acted:
            return False
        cost = tactic.cost or 0
        if tactic.currency == "points":
            return self.points >= cost
        return tactic.id not in self.gold_used and self.wallet(None) >= cost

    def use_tactic(self, unit: Unit, tactic: s.Tactic) -> bool:
        if not self.tactic_ok(unit, tactic):
            return False
        cost = tactic.cost or 0
        if tactic.currency == "points":
            self.points -= cost
        else:
            self.wallet(-cost)
            self.gold_used.add(tactic.id)
        unit.tactic_used = True
        self.log.append(Event(unit.id, None, 0, f"Тактика: {tactic.name}", "info"))
        targets = [unit] if tactic.target == "unit" else self.alive_party() if tactic.target == "party" else self.alive_enemies()
        for t in targets:
            for e in tactic.effect:
                if isinstance(e, s.EffDamage):
                    if t.side == "enemy" and t.alive:
                        self.hurt(unit, t, e.damage, tactic.name)
                elif isinstance(e, s.EffModStat) and e.mod_stat in ("attack", "defense") and t.side == "enemy":
                    t.buffs.append(Buff(e.mod_stat, e.delta, tactic.duration))
                    self.log.append(Event(unit.id, t.id, 0, f"{tactic.name}: {t.name} {e.delta:+d}", "buff"))
                elif t.side == "party":
                    self.apply_self(t, e, tactic.duration, tactic.name)
        unit.move_bonus += tactic.move_bonus
        return True

    # --- смена фаз и ИИ врагов ---

    def end_turn(self) -> None:
        if self.result is not None:
            return
        for u in self.alive_enemies():
            _tick_buffs(u)
        for e in list(self.enemies):
            if self.result is not None:
                return
            if e.alive:
                self.enemy_turn(e)
        self.round += 1
        if self.round > MAX_ROUNDS:
            self.result = "lose"
            self.log.append(Event("", None, 0, "Силы на исходе — бой проигран.", "info"))
            return
        for u in self.alive_party():
            _tick_buffs(u)
            u.focus = min(u.max_focus, u.focus + FOCUS_REGEN)
            u.moved = u.acted = u.tactic_used = False
            u.move_bonus = 0

    def enemy_target(self, e: Unit) -> Unit:
        def key(p: Unit):
            d = self.field.path_dist(e.pos, p.pos)
            return (FAR + manhattan(e.pos, p.pos) if d is None else d, p.hp, self.party.index(p))
        return min(self.alive_party(), key=key)

    def best_cell(self, unit: Unit, target: Unit, reach_range: int) -> Cell:
        """Клетка для хода: оттуда достаём цель (спина → фланг → перед, ближе, меньший y, x), иначе ближе к цели."""
        if manhattan(unit.pos, target.pos) <= reach_range:
            return unit.pos
        reach = self.field.reachable(unit.pos, unit.move + unit.move_bonus, self.occupied(unit))
        hits = [c for c in reach if manhattan(c, target.pos) <= reach_range]
        if hits:
            return min(hits, key=lambda c: (DIRECTION_RANK[direction(c, target)], reach[c][0], c[1], c[0]))

        def closer(c: Cell):
            d = self.field.path_dist(c, target.pos)
            return (FAR if d is None else d, reach[c][0], c[1], c[0])
        return min(reach, key=closer)

    def enemy_turn(self, e: Unit) -> None:
        e.turn += 1
        target = self.enemy_target(e)
        cell = self.best_cell(e, target, e.range)
        if cell != e.pos:
            reach = self.field.reachable(e.pos, e.move, self.occupied(e))
            self._walk(e, cell, reach)
            self.log.append(Event(e.id, None, 0, "", "move"))
        ability = next((a for a in e.abilities if e.turn % a.every_n_turns == 0), None)
        dist = manhattan(e.pos, target.pos)
        has_damage = ability is not None and any(isinstance(x, s.EffDamage) for x in ability.effect)
        if ability and (not has_damage or dist <= max(e.range, ABILITY_RANGE)):
            for x in ability.effect:
                if self.result is not None:
                    return
                if isinstance(x, s.EffDamage):
                    e.facing = face_towards(e.pos, target.pos)
                    self.hurt(e, target, x.damage, f"{e.name} — {ability.name}")
                elif isinstance(x, s.EffHeal):
                    before = e.hp
                    e.hp = min(e.max_hp, e.hp + x.heal)
                    self.log.append(Event(e.id, e.id, before - e.hp, f"{e.name} — {ability.name}: +{e.hp - before}", "heal"))
                elif isinstance(x, s.EffModStat) and x.mod_stat in ("attack", "defense"):
                    setattr(e, x.mod_stat, max(0, getattr(e, x.mod_stat) + x.delta))
                    self.log.append(Event(e.id, e.id, 0, f"{e.name} — {ability.name}", "buff"))
            return
        if dist <= e.range:
            e.facing = face_towards(e.pos, target.pos)
            dmg, side, high = self.strike(e, target, roll_damage(e.stat("attack"), target.stat("defense"), self.rng))
            self.hurt(e, target, dmg, f"{e.name} бьёт", side, high)


def _tick_buffs(u: Unit) -> None:
    for b in u.buffs:
        b.phases -= 1
    u.buffs = [b for b in u.buffs if b.phases > 0]


# --- сборка бойцов -------------------------------------------------------------


def enemy_move(enemy: s.Enemy) -> int:
    size = getattr(enemy.appearance, "size", None)
    return MOVE_BY_SIZE.get(size, PARTY_MOVE) if size else PARTY_MOVE


def weak_bonus(attacker: Unit, defender: Unit, bane: str | None = None) -> float:
    """Надбавка к множителю урона за слабость врага: знание +25%, оружие (или бомба) против неё +50%."""
    if attacker.side != "party" or not defender.weak:
        return 0.0
    used = bane if bane is not None else attacker.bane
    return (KNOWN_WEAK_BONUS if defender.weak_known else 0.0) + (BANE_BONUS if used == defender.weak else 0.0)


def companion_stats(base_hp: int, base_attack: int, base_defense: int, base_focus: int) -> tuple[int, int, int, int]:
    return max(1, round(base_hp * COMPANION_HP)), max(1, round(base_attack * COMPANION_ATTACK)), base_defense, base_focus


def make_enemies(foe: s.Foe, enemies: dict[str, s.Enemy], arena: s.Arena, known: set[str] = frozenset()) -> list[Unit]:
    out = []
    for i, enemy_id in enumerate(foe.enemies):
        e = enemies[enemy_id]
        x, y = arena.enemies[i]
        out.append(Unit(id=f"e{i}", name=e.name, side="enemy", kind="enemy", hp=e.hp, max_hp=e.hp, attack=e.attack,
                        defense=e.defense, focus=0, max_focus=0, move=enemy_move(e), range=e.range, pos=(x, y),
                        facing=(-1, 0), abilities=e.abilities, weak=e.weakness.tag if e.weakness else None,
                        weak_known=enemy_id in known))
    return out


# --- бот отряда (плейтест) -------------------------------------------------------


def _heal(effects: list[s.Effect]) -> int:
    return sum(e.heal for e in effects if isinstance(e, s.EffHeal))


def _damage(effects: list[s.Effect]) -> int:
    return sum(e.damage for e in effects if isinstance(e, s.EffDamage))


def play_party_turn(b: Battle, skills: dict[str, s.Skill], items: dict[str, s.Item], inventory, take) -> None:
    """Бот за каждого бойца отряда (SPEC §7.2), затем конец хода."""
    for unit in b.alive_party():
        if b.result is not None:
            return
        low = unit.hp < unit.max_hp * LOW_HP_RATIO
        usable = [t for t in b.tactics if t.currency == "points" and b.tactic_ok(unit, t)]
        if low:
            heal_t = sorted((t for t in usable if _heal(t.effect) > 0 and t.target in ("unit", "party")), key=lambda t: t.cost or 0)
            if heal_t:
                b.use_tactic(unit, heal_t[0])
                low = unit.hp < unit.max_hp * LOW_HP_RATIO
        if low:
            heal_items = [items[i] for i, n in sorted(inventory.items()) if n > 0 and i in items
                          and items[i].kind == "consumable" and _heal(items[i].effect) > 0]
            if heal_items and b.item(unit, max(heal_items, key=lambda i: _heal(i.effect)), None, take):
                continue
            heal_s = [skills[k] for k in unit.skills if k in skills and skills[k].target == "self"
                      and _heal(skills[k].effect) > 0 and skills[k].cost_focus <= unit.focus]
            if heal_s and b.skill(unit, max(heal_s, key=lambda k: _heal(k.effect)), None):
                continue
        foes = b.alive_enemies()
        if not foes:
            return

        def foe_key(f: Unit):
            d = b.field.path_dist(unit.pos, f.pos)
            return (FAR + manhattan(unit.pos, f.pos) if d is None else d, f.hp, b.enemies.index(f))
        target = min(foes, key=foe_key)
        strikes = [skills[k] for k in unit.skills if k in skills and skills[k].target == "enemy"
                   and _damage(skills[k].effect) > 0 and skills[k].cost_focus <= unit.focus]
        best = max(strikes, key=lambda k: _damage(k.effect)) if strikes else None
        plain = max(1, unit.stat("attack") - target.stat("defense") // 2)
        use_skill = best is not None and _damage(best.effect) > plain
        reach = SKILL_RANGE if use_skill else unit.range
        cell = b.best_cell(unit, target, reach)
        if cell != unit.pos:
            b.move(unit, cell)
        if manhattan(unit.pos, target.pos) > reach:
            dash = next((t for t in usable if t.move_bonus > 0 and b.tactic_ok(unit, t)), None)
            if dash and not unit.moved:
                b.use_tactic(unit, dash)
            b.defend(unit)
            continue
        buff = next((t for t in sorted(usable, key=lambda t: t.cost or 0)
                     if b.tactic_ok(unit, t) and t.target in ("unit", "party")
                     and any(isinstance(e, s.EffModStat) and e.mod_stat == "attack" and e.delta > 0 for e in t.effect)), None)
        if buff:
            b.use_tactic(unit, buff)
        if use_skill:
            b.skill(unit, best, target)
        else:
            b.attack(unit, target)
    b.end_turn()
