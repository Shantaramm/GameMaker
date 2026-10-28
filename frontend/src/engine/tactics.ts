// Тактический бой на изометрическом поле (SPEC §5.9). Правила и ИИ врагов — зеркало
// backend/app/engine/tactics.py: те же константы, порядок соседей, ключи выбора клеток и целей.
// Меняя правило здесь, меняй его и там.

import type { Arena, EnemyAbility, Item, Skill, Tactic } from "../types/game";
import { check } from "./conditions";
import { passiveHeard } from "./inner";
import { count, effective, type GameState, skillValue } from "./state";
import type { Condition, Effect, MapObject, World } from "./world";

type Foe = Extract<MapObject, { type: "enemy" }>;
export type Cell = [number, number];

export const PARTY_MOVE = 3;
export const MOVE_BY_SIZE: Record<string, number> = { small: 4, medium: 3, large: 2 };
export const STYLE_RANGE: Record<string, number> = { melee: 1, support: 2, ranged: 3 };
export const SKILL_RANGE = 3;
export const ABILITY_RANGE = 3;
export const SKILL_BUFF_PHASES = 2;
export const MAX_ROUNDS = 30;
export const MAX_POINTS = 12;
export const FLANK_BONUS = 0.25;
export const BACK_BONUS = 0.5;
export const HIGH_BONUS = 0.2;
export const KNOWN_WEAK_BONUS = 0.25; // слабость врага известна (§5.12)
export const BANE_BONUS = 0.5; // оружие или бомба против этой слабости
export const COMPANION_HP = 0.7;
export const COMPANION_ATTACK = 0.8;
export const FLEE_CHANCE = 0.5;
export const DAMAGE_SPREAD = 0.2;
export const FOCUS_REGEN = 1;
export const REST_HEAL = 0.3; // после победы герой восстанавливает долю максимума HP
const FAR = 1000;
export const NEIGHBOURS: Cell[] = [[1, 0], [-1, 0], [0, 1], [0, -1]];

/** Округление как у Python round() для неотрицательных чисел: половины — к чётному. */
export function pyRound(x: number): number {
  const f = Math.floor(x);
  const d = x - f;
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

export function rollDamage(attack: number, defense: number, random: () => number): number {
  const base = Math.max(1, attack - Math.floor(defense / 2));
  return Math.max(1, pyRound(base * (1 - DAMAGE_SPREAD + random() * 2 * DAMAGE_SPREAD)));
}

export const manhattan = (a: Cell, b: Cell) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
const same = (a: Cell, b: Cell) => a[0] === b[0] && a[1] === b[1];
const key = (c: Cell) => `${c[0]},${c[1]}`;

export function faceTowards(src: Cell, dst: Cell): Cell {
  const dx = dst[0] - src[0];
  const dy = dst[1] - src[1];
  return Math.abs(dx) >= Math.abs(dy) ? [Math.sign(dx), 0] : [0, Math.sign(dy)];
}

export interface Buff { stat: "attack" | "defense"; delta: number; phases: number }

export interface Unit {
  id: string;
  name: string;
  side: "party" | "enemy";
  kind: "hero" | "companion" | "enemy";
  hp: number;
  maxHp: number;
  attack: number;
  defense: number;
  focus: number;
  maxFocus: number;
  move: number;
  range: number;
  pos: Cell;
  facing: Cell;
  abilities: EnemyAbility[];
  skills: string[];
  buffs: Buff[];
  turn: number;
  moved: boolean;
  acted: boolean;
  tacticUsed: boolean;
  moveBonus: number;
  /** id персонажа или врага — по нему рисуется спрайт */
  look: string;
  bane?: string | null; // отряд: против какой слабости оружие (§5.12)
  weak?: string | null; // враг: его слабость
  weakKnown?: boolean; // враг: слабость в бестиарии
}

/** Надбавка к множителю урона за слабость врага: знание +25%, оружие (или бомба) против неё +50% — как weak_bonus в tactics.py. */
export function weakBonus(attacker: Unit, defender: Unit, bane: string | null = null): number {
  if (attacker.side !== "party" || !defender.weak) return 0;
  const used = bane ?? attacker.bane ?? null;
  return (defender.weakKnown ? KNOWN_WEAK_BONUS : 0) + (used === defender.weak ? BANE_BONUS : 0);
}

export const alive = (u: Unit) => u.hp > 0;
export function stat(u: Unit, name: "attack" | "defense"): number {
  return Math.max(0, u[name] + u.buffs.filter((b) => b.stat === name).reduce((s, b) => s + b.delta, 0));
}

export type Reach = Map<string, { steps: number; from: Cell | null; cell: Cell }>;

export class Field {
  readonly w: number;
  readonly h: number;
  readonly heights: number[][];
  readonly blocked = new Set<string>();

  constructor(readonly arena: Arena) {
    this.w = arena.width;
    this.h = arena.height;
    this.heights = arena.cells.map((row) => [...row].map((c) => (c === "#" ? 0 : Number(c))));
    arena.cells.forEach((row, y) => [...row].forEach((c, x) => c === "#" && this.blocked.add(key([x, y]))));
  }

  height(c: Cell): number {
    return this.heights[c[1]][c[0]];
  }

  stepOk(a: Cell, b: Cell): boolean {
    const [x, y] = b;
    return x >= 0 && x < this.w && y >= 0 && y < this.h && !this.blocked.has(key(b)) && Math.abs(this.height(a) - this.height(b)) <= 1;
  }

  /** Клетка → шаги и откуда пришли; сквозь бойцов нельзя. Порядок обхода — как в Python (вставка в Map). */
  reachable(start: Cell, steps: number, occupied: Set<string>): Reach {
    const out: Reach = new Map([[key(start), { steps: 0, from: null, cell: start }]]);
    const queue: Cell[] = [start];
    while (queue.length) {
      const cur = queue.shift()!;
      const d = out.get(key(cur))!.steps;
      if (d === steps) continue;
      for (const [dx, dy] of NEIGHBOURS) {
        const nxt: Cell = [cur[0] + dx, cur[1] + dy];
        const k = key(nxt);
        if (!out.has(k) && !occupied.has(k) && this.stepOk(cur, nxt)) {
          out.set(k, { steps: d + 1, from: cur, cell: nxt });
          queue.push(nxt);
        }
      }
    }
    return out;
  }

  pathDist(a: Cell, b: Cell): number | null {
    if (same(a, b)) return 0;
    const seen = new Map<string, number>([[key(a), 0]]);
    const queue: Cell[] = [a];
    while (queue.length) {
      const cur = queue.shift()!;
      for (const [dx, dy] of NEIGHBOURS) {
        const nxt: Cell = [cur[0] + dx, cur[1] + dy];
        const k = key(nxt);
        if (!seen.has(k) && this.stepOk(cur, nxt)) {
          seen.set(k, seen.get(key(cur))! + 1);
          if (same(nxt, b)) return seen.get(k)!;
          queue.push(nxt);
        }
      }
    }
    return null;
  }
}

export type Side = "front" | "flank" | "back";
export function direction(attacker: Cell, defender: Unit): Side {
  const vx = attacker[0] - defender.pos[0];
  const vy = attacker[1] - defender.pos[1];
  const dot = vx * defender.facing[0] + vy * defender.facing[1];
  return dot > 0 ? "front" : dot === 0 ? "flank" : "back";
}
const DIRECTION_RANK: Record<Side, number> = { back: 0, flank: 1, front: 2 };

/** Лексикографическое сравнение ключей сортировки (как кортежи в Python). */
function minBy<T>(items: T[], keyOf: (t: T) => number[]): T {
  let best = items[0];
  let bestKey = keyOf(best);
  for (const it of items.slice(1)) {
    const k = keyOf(it);
    for (let i = 0; i < k.length; i++) {
      if (k[i] !== bestKey[i]) {
        if (k[i] < bestKey[i]) {
          best = it;
          bestKey = k;
        }
        break;
      }
    }
  }
  return best;
}

export interface BattleEvent {
  actor: string;
  target: string | null;
  amount: number;
  text: string;
  kind: "hit" | "heal" | "buff" | "move" | "info";
  side?: Side;
  high?: boolean;
  path?: Cell[];
}

export class Battle {
  readonly field: Field;
  points = 0;
  round = 1;
  result: "win" | "lose" | "fled" | null = null;
  readonly goldUsed = new Set<string>();
  log: BattleEvent[] = [];

  constructor(
    readonly arena: Arena,
    readonly party: Unit[],
    readonly enemies: Unit[],
    readonly tactics: Tactic[],
    readonly canFlee: boolean,
    readonly random: () => number,
    /** wallet(delta) меняет золото героя и возвращает остаток; wallet(null) — только остаток */
    readonly wallet: (delta: number | null) => number,
  ) {
    this.field = new Field(arena);
  }

  // --- справочное ---

  get units(): Unit[] {
    return [...this.party, ...this.enemies].filter(alive);
  }

  occupied(except?: Unit): Set<string> {
    return new Set(this.units.filter((u) => u !== except).map((u) => key(u.pos)));
  }

  moves(unit: Unit): Reach {
    if (unit.moved || unit.acted) return new Map([[key(unit.pos), { steps: 0, from: null, cell: unit.pos }]]);
    return this.field.reachable(unit.pos, unit.move + unit.moveBonus, this.occupied(unit));
  }

  aliveEnemies(): Unit[] {
    return this.enemies.filter(alive);
  }

  aliveParty(): Unit[] {
    return this.party.filter(alive);
  }

  hero(): Unit {
    return this.party.find((u) => u.kind === "hero")!;
  }

  unitAt(c: Cell): Unit | undefined {
    return this.units.find((u) => same(u.pos, c));
  }

  // --- урон ---

  strike(attacker: Unit, defender: Unit, base: number): { dmg: number; side: Side; high: boolean } {
    const side = direction(attacker.pos, defender);
    const high = this.field.height(attacker.pos) > this.field.height(defender.pos);
    const mult = 1 + (side === "back" ? BACK_BONUS : side === "flank" ? FLANK_BONUS : 0) + (high ? HIGH_BONUS : 0) + weakBonus(attacker, defender);
    return { dmg: Math.max(1, Math.floor(base * mult + 0.5)), side, high };
  }

  /** Сколько примерно снимет атака отсюда — для подсказки игроку (без разброса). */
  preview(attacker: Unit, defender: Unit, from: Cell = attacker.pos): { dmg: number; side: Side; high: boolean } {
    const base = Math.max(1, stat(attacker, "attack") - Math.floor(stat(defender, "defense") / 2));
    const probe = { ...attacker, pos: from };
    return this.strike(probe, defender, base);
  }

  private hurt(attacker: Unit, defender: Unit, dmg: number, label: string, side: Side = "front", high = false): void {
    defender.hp -= dmg;
    const note = (side === "flank" ? " (фланг)" : side === "back" ? " (в спину)" : "") + (high ? " (сверху)" : "");
    this.log.push({ actor: attacker.id, target: defender.id, amount: dmg, text: `${label}: ${defender.name} −${dmg}${note}`, kind: "hit", side, high });
    if (attacker.side === "party") this.gain(1 + (side !== "front" ? 1 : 0) + (high ? 1 : 0));
    if (alive(defender)) return;
    if (defender.side === "enemy") {
      this.log.push({ actor: attacker.id, target: defender.id, amount: 0, text: `${defender.name} повержен`, kind: "info" });
      if (attacker.side === "party") this.gain(2);
      if (!this.aliveEnemies().length) this.result = "win";
    } else if (defender.kind === "hero") {
      defender.hp = 0;
      this.result = "lose";
    } else {
      this.log.push({ actor: attacker.id, target: defender.id, amount: 0, text: `${defender.name} выбывает из боя`, kind: "info" });
    }
  }

  private gain(n: number): void {
    this.points = Math.min(MAX_POINTS, this.points + n);
  }

  private applySelf(unit: Unit, e: Effect, phases: number, label: string): void {
    if ("heal" in e) {
      const before = unit.hp;
      unit.hp = Math.min(unit.maxHp, unit.hp + e.heal);
      this.log.push({ actor: unit.id, target: unit.id, amount: before - unit.hp, text: `${label}: ${unit.name} +${unit.hp - before}`, kind: "heal" });
    } else if ("mod_stat" in e && (e.mod_stat === "attack" || e.mod_stat === "defense")) {
      unit.buffs.push({ stat: e.mod_stat, delta: e.delta, phases });
      const name = e.mod_stat === "attack" ? "атака" : "защита";
      this.log.push({ actor: unit.id, target: unit.id, amount: 0, text: `${label}: ${unit.name} ${name} ${e.delta >= 0 ? "+" : ""}${e.delta}`, kind: "buff" });
    } else if ("mod_stat" in e && e.mod_stat === "hp" && e.delta > 0) {
      this.applySelf(unit, { heal: e.delta }, phases, label);
    } else if ("mod_stat" in e && e.mod_stat === "focus") {
      unit.focus = Math.max(0, Math.min(unit.maxFocus, unit.focus + e.delta));
    }
  }

  // --- действия отряда ---

  canAct(unit: Unit): boolean {
    return this.result === null && unit.side === "party" && alive(unit) && !unit.acted;
  }

  move(unit: Unit, cell: Cell): boolean {
    if (!this.canAct(unit) || unit.moved) return false;
    const reach = this.moves(unit);
    if (!reach.has(key(cell)) || same(cell, unit.pos)) return false;
    this.walk(unit, cell, reach);
    unit.moved = true;
    return true;
  }

  private walk(unit: Unit, cell: Cell, reach: Reach): void {
    const prev = reach.get(key(cell))!.from;
    if (prev) unit.facing = [cell[0] - prev[0], cell[1] - prev[1]];
    unit.pos = cell;
  }

  /** Путь до клетки (для анимации): от текущей позиции к цели. */
  path(reach: Reach, cell: Cell): Cell[] {
    const out: Cell[] = [];
    let cur: Cell | null = cell;
    while (cur) {
      out.unshift(cur);
      cur = reach.get(key(cur))?.from ?? null;
    }
    return out;
  }

  attack(unit: Unit, target: Unit): boolean {
    if (!this.canAct(unit) || !alive(target) || manhattan(unit.pos, target.pos) > unit.range) return false;
    unit.facing = faceTowards(unit.pos, target.pos);
    const { dmg, side, high } = this.strike(unit, target, rollDamage(stat(unit, "attack"), stat(target, "defense"), this.random));
    this.hurt(unit, target, dmg, "Удар", side, high);
    unit.acted = true;
    return true;
  }

  skill(unit: Unit, skill: Skill, target: Unit | null): boolean {
    if (!this.canAct(unit) || !unit.skills.includes(skill.id) || unit.focus < skill.cost_focus) return false;
    if (skill.target === "enemy" && (!target || !alive(target) || manhattan(unit.pos, target.pos) > SKILL_RANGE)) return false;
    unit.focus -= skill.cost_focus;
    for (const e of skill.effect as Effect[]) {
      if (skill.target === "enemy" && "damage" in e) {
        unit.facing = faceTowards(unit.pos, target!.pos);
        const { dmg, side, high } = this.strike(unit, target!, e.damage);
        this.hurt(unit, target!, dmg, skill.name, side, high);
      } else if (skill.target === "enemy" && "mod_stat" in e && (e.mod_stat === "attack" || e.mod_stat === "defense")) {
        target!.buffs.push({ stat: e.mod_stat, delta: e.delta, phases: SKILL_BUFF_PHASES });
        this.log.push({ actor: unit.id, target: target!.id, amount: 0, text: `${skill.name}: ${target!.name} ${e.delta >= 0 ? "+" : ""}${e.delta}`, kind: "buff" });
      } else if (skill.target === "self") {
        this.applySelf(unit, e, SKILL_BUFF_PHASES, skill.name);
      }
    }
    unit.acted = true;
    return true;
  }

  /** take(itemId) списывает предмет из сумки героя. */
  item(unit: Unit, item: Item, target: Unit | null, take: (id: string) => boolean): boolean {
    if (!this.canAct(unit) || item.kind !== "consumable") return false;
    const effects = (item.effect ?? []) as Effect[];
    const hits = effects.some((e) => "damage" in e);
    if (hits && (!target || !alive(target) || manhattan(unit.pos, target.pos) > SKILL_RANGE)) return false;
    if (!take(item.id)) return false;
    for (const e of effects) {
      if ("damage" in e) this.hurt(unit, target!, Math.floor(e.damage * (1 + weakBonus(unit, target!, item.bane ?? null)) + 0.5), item.name);
      else this.applySelf(unit, e, SKILL_BUFF_PHASES, item.name);
    }
    unit.acted = true;
    return true;
  }

  defend(unit: Unit): boolean {
    if (!this.canAct(unit)) return false;
    const delta = Math.max(2, Math.floor(unit.defense / 2));
    unit.buffs.push({ stat: "defense", delta, phases: 1 });
    this.log.push({ actor: unit.id, target: unit.id, amount: 0, text: `${unit.name} в защите: защита +${delta}`, kind: "buff" });
    unit.acted = true;
    return true;
  }

  flee(unit: Unit): boolean {
    if (!this.canAct(unit) || unit.kind !== "hero") return false;
    unit.acted = true;
    if (this.canFlee && this.random() < FLEE_CHANCE) {
      this.result = "fled";
      this.log.push({ actor: unit.id, target: null, amount: 0, text: "Удалось сбежать!", kind: "info" });
    } else {
      this.log.push({ actor: unit.id, target: null, amount: 0, text: this.canFlee ? "Сбежать не вышло." : "Отсюда не сбежать.", kind: "info" });
    }
    return true;
  }

  tacticOk(unit: Unit, t: Tactic): boolean {
    if (this.result !== null || unit.side !== "party" || !alive(unit) || unit.tacticUsed || unit.acted) return false;
    const cost = t.cost ?? 0;
    if ((t.currency ?? "points") === "points") return this.points >= cost;
    return !this.goldUsed.has(t.id) && this.wallet(null) >= cost;
  }

  useTactic(unit: Unit, t: Tactic): boolean {
    if (!this.tacticOk(unit, t)) return false;
    const cost = t.cost ?? 0;
    if ((t.currency ?? "points") === "points") this.points -= cost;
    else {
      this.wallet(-cost);
      this.goldUsed.add(t.id);
    }
    unit.tacticUsed = true;
    this.log.push({ actor: unit.id, target: null, amount: 0, text: `Тактика: ${t.name}`, kind: "info" });
    const target = t.target ?? "unit";
    const targets = target === "unit" ? [unit] : target === "party" ? this.aliveParty() : this.aliveEnemies();
    const duration = t.duration ?? 1;
    for (const u of targets) {
      for (const e of (t.effect ?? []) as Effect[]) {
        if ("damage" in e) {
          if (u.side === "enemy" && alive(u)) this.hurt(unit, u, e.damage, t.name);
        } else if ("mod_stat" in e && (e.mod_stat === "attack" || e.mod_stat === "defense") && u.side === "enemy") {
          u.buffs.push({ stat: e.mod_stat, delta: e.delta, phases: duration });
          this.log.push({ actor: unit.id, target: u.id, amount: 0, text: `${t.name}: ${u.name} ${e.delta >= 0 ? "+" : ""}${e.delta}`, kind: "buff" });
        } else if (u.side === "party") {
          this.applySelf(u, e, duration, t.name);
        }
      }
    }
    unit.moveBonus += t.move_bonus ?? 0;
    return true;
  }

  // --- смена фаз и ИИ врагов ---

  endTurn(): void {
    if (this.result !== null) return;
    for (const u of this.aliveEnemies()) tickBuffs(u);
    for (const e of this.enemies) {
      if (this.result !== null) return;
      if (alive(e)) this.enemyTurn(e);
    }
    this.round += 1;
    if (this.round > MAX_ROUNDS) {
      this.result = "lose";
      this.log.push({ actor: "", target: null, amount: 0, text: "Силы на исходе — бой проигран.", kind: "info" });
      return;
    }
    for (const u of this.aliveParty()) {
      tickBuffs(u);
      u.focus = Math.min(u.maxFocus, u.focus + FOCUS_REGEN);
      u.moved = u.acted = u.tacticUsed = false;
      u.moveBonus = 0;
    }
  }

  enemyTarget(e: Unit): Unit {
    return minBy(this.aliveParty(), (p) => {
      const d = this.field.pathDist(e.pos, p.pos);
      return [d === null ? FAR + manhattan(e.pos, p.pos) : d, p.hp, this.party.indexOf(p)];
    });
  }

  bestCell(unit: Unit, target: Unit, reachRange: number): Cell {
    if (manhattan(unit.pos, target.pos) <= reachRange) return unit.pos;
    const reach = this.field.reachable(unit.pos, unit.move + unit.moveBonus, this.occupied(unit));
    const cells = [...reach.values()];
    const hits = cells.filter((r) => manhattan(r.cell, target.pos) <= reachRange);
    if (hits.length) return minBy(hits, (r) => [DIRECTION_RANK[direction(r.cell, target)], r.steps, r.cell[1], r.cell[0]]).cell;
    return minBy(cells, (r) => {
      const d = this.field.pathDist(r.cell, target.pos);
      return [d === null ? FAR : d, r.steps, r.cell[1], r.cell[0]];
    }).cell;
  }

  enemyTurn(e: Unit): void {
    e.turn += 1;
    const target = this.enemyTarget(e);
    const cell = this.bestCell(e, target, e.range);
    if (!same(cell, e.pos)) {
      const reach = this.field.reachable(e.pos, e.move, this.occupied(e));
      const path = this.path(reach, cell);
      this.walk(e, cell, reach);
      this.log.push({ actor: e.id, target: null, amount: 0, text: "", kind: "move", path });
    }
    const ability = e.abilities.find((a) => e.turn % a.every_n_turns === 0);
    const dist = manhattan(e.pos, target.pos);
    const hasDamage = !!ability && (ability.effect as Effect[]).some((x) => "damage" in x);
    if (ability && (!hasDamage || dist <= Math.max(e.range, ABILITY_RANGE))) {
      for (const x of ability.effect as Effect[]) {
        if (this.result !== null) return;
        if ("damage" in x) {
          e.facing = faceTowards(e.pos, target.pos);
          this.hurt(e, target, x.damage, `${e.name} — ${ability.name}`);
        } else if ("heal" in x) {
          const before = e.hp;
          e.hp = Math.min(e.maxHp, e.hp + x.heal);
          this.log.push({ actor: e.id, target: e.id, amount: before - e.hp, text: `${e.name} — ${ability.name}: +${e.hp - before}`, kind: "heal" });
        } else if ("mod_stat" in x && (x.mod_stat === "attack" || x.mod_stat === "defense")) {
          e[x.mod_stat] = Math.max(0, e[x.mod_stat] + x.delta);
          this.log.push({ actor: e.id, target: e.id, amount: 0, text: `${e.name} — ${ability.name}`, kind: "buff" });
        }
      }
      return;
    }
    if (dist <= e.range) {
      e.facing = faceTowards(e.pos, target.pos);
      const { dmg, side, high } = this.strike(e, target, rollDamage(stat(e, "attack"), stat(target, "defense"), this.random));
      this.hurt(e, target, dmg, `${e.name} бьёт`, side, high);
    }
  }
}

function tickBuffs(u: Unit): void {
  for (const b of u.buffs) b.phases -= 1;
  u.buffs = u.buffs.filter((b) => b.phases > 0);
}

// --- сборка боя из состояния игры (как party_units / make_enemies / start_battle в simulator.py) ---

function base(u: Partial<Unit> & Pick<Unit, "id" | "name" | "side" | "kind" | "hp" | "maxHp" | "attack" | "defense" | "move" | "range" | "pos" | "facing" | "look">): Unit {
  return { focus: 0, maxFocus: 0, abilities: [], skills: [], buffs: [], turn: 0, moved: false, acted: false, tacticUsed: false, moveBonus: 0, ...u };
}

export function partyUnits(state: GameState, world: World, arena: Arena): Unit[] {
  const eff = effective(state, world);
  const weapon = world.items.get(state.equipment.hand ?? "");
  const hero = world.game.hero;
  const units: Unit[] = [base({
    id: "hero", name: hero.name, side: "party", kind: "hero", hp: state.hp, maxHp: eff.maxHp, attack: eff.attack,
    defense: eff.defense, focus: eff.maxFocus, maxFocus: eff.maxFocus, move: PARTY_MOVE, range: weapon?.equip?.range ?? 1,
    pos: [...arena.party[0]] as Cell, facing: [1, 0], skills: [...state.skills].sort(), look: hero.id, bane: weapon?.bane ?? null,
  })];
  for (const c of world.game.characters ?? []) {
    if (c.role !== "companion" || !check(c.joins as Condition | null, state, world) || units.length >= arena.party.length) continue;
    const hp = Math.max(1, pyRound(state.maxHp * COMPANION_HP));
    const atk = Math.max(1, pyRound(state.attack * COMPANION_ATTACK));
    const style = c.combat?.style ?? "melee";
    units.push(base({
      id: c.id, name: c.name, side: "party", kind: "companion", hp, maxHp: hp, attack: atk, defense: state.defense,
      focus: state.maxFocus, maxFocus: state.maxFocus, move: PARTY_MOVE, range: STYLE_RANGE[style],
      pos: [...arena.party[units.length]] as Cell, facing: [1, 0], skills: [...(c.combat?.skills ?? [])], look: c.id,
    }));
  }
  return units;
}

export function enemyUnits(foe: Foe, world: World, arena: Arena, known: string[] = []): Unit[] {
  return foe.enemies.map((id, i) => {
    const e = world.enemies.get(id)!;
    const size = "size" in e.appearance ? e.appearance.size : null;
    return base({
      id: `e${i}`, name: e.name, side: "enemy", kind: "enemy", hp: e.hp!, maxHp: e.hp!, attack: e.attack!, defense: e.defense!,
      move: size ? MOVE_BY_SIZE[size] ?? PARTY_MOVE : PARTY_MOVE, range: e.range ?? 1, pos: [...arena.enemies[i]] as Cell,
      facing: [-1, 0], abilities: e.abilities ?? [], look: id, weak: e.weakness?.tag ?? null, weakKnown: known.includes(id),
    });
  });
}

export function availableTactics(state: GameState, world: World): Tactic[] {
  return (world.game.tactics ?? []).filter((t) => check(t.unlock as Condition | null, state, world));
}

/** Перед боем навык (обычно Знания) сам вспоминает слабость врага — как recall_weaknesses в simulator.py. */
export function recallWeaknesses(foe: Foe, state: GameState, world: World): string[] {
  const out: string[] = [];
  for (const id of new Set(foe.enemies)) {
    const w = world.enemies.get(id)?.weakness;
    if (!w || state.bestiary.includes(id) || !passiveHeard(skillValue(state, world, w.skill ?? "knowledge"), w.difficulty ?? "medium")) continue;
    state.bestiary.push(id);
    out.push(`${world.skillName(w.skill ?? "knowledge").toUpperCase()}: ${w.hint}`);
  }
  return out;
}

/** Бой по объекту-врагу; золото тратится прямо из state. */
export function startBattle(foe: Foe, state: GameState, world: World, random: () => number): Battle {
  const arena = world.game.arenas?.[foe.id];
  if (!arena) throw new Error(`нет поля боя для ${foe.id}`);
  const wallet = (delta: number | null) => {
    if (delta !== null) state.gold += delta;
    return state.gold;
  };
  const recalled = recallWeaknesses(foe, state, world);
  const battle = new Battle(arena, partyUnits(state, world, arena), enemyUnits(foe, world, arena, state.bestiary), availableTactics(state, world), !!foe.can_flee, random, wallet);
  for (const text of recalled) battle.log.push({ actor: "hero", target: "hero", amount: 0, text, kind: "info" });
  return battle;
}

export function takeItem(state: GameState): (id: string) => boolean {
  return (id) => {
    if (count(state, id) <= 0) return false;
    state.inventory[id] -= 1;
    if (state.inventory[id] === 0) delete state.inventory[id];
    return true;
  };
}

export function rewards(foe: Foe, world: World): { xp: number; gold: number } {
  const enemies = foe.enemies.map((id) => world.enemies.get(id)!);
  return { xp: enemies.reduce((s, e) => s + (e.xp ?? 0), 0), gold: enemies.reduce((s, e) => s + (e.gold ?? 0), 0) };
}
