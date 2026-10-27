// Состояние игрока и сохранение в localStorage (SPEC §5.7).

import { type CheckRecord, HEALTH_BASE, MORALE_BASE, SKILL_KEYS } from "./inner";
import { SLOTS, type Slot, type World } from "./world";

export interface GameState {
  version: 2;
  location: string;
  floor: number;
  x: number;
  cameFrom: string | null;
  // базовые статы без экипировки
  hp: number;
  maxHp: number;
  attack: number;
  defense: number;
  focus: number;
  maxFocus: number;
  gold: number;
  xp: number;
  level: number;
  inventory: Record<string, number>;
  equipment: Partial<Record<Slot, string>>;
  skills: string[];
  flags: Record<string, boolean>;
  defeated: string[];
  opened: string[];
  used: string[];
  visited: string[];
  ending: string | null;
  // внутренние навыки (§5.10)
  morale: number;
  inner: Record<string, number>;
  skillPoints: number;
  checks: Record<string, CheckRecord>;
  examined: string[];
  questsRewarded: string[];
}

export interface Effective {
  attack: number;
  defense: number;
  maxHp: number;
  maxFocus: number;
  maxMorale: number;
}

export function newState(world: World): GameState {
  const g = world.game;
  const t = g.stats_template!;
  const state: GameState = {
    version: 2,
    location: g.start_location,
    floor: 0,
    x: 0,
    cameFrom: null,
    hp: t.hp, maxHp: t.hp, attack: t.attack, defense: t.defense, focus: t.focus, maxFocus: t.focus,
    gold: g.start_gold ?? 0, xp: 0, level: 1,
    inventory: {},
    equipment: {},
    skills: [...(g.start_skills ?? [])],
    flags: Object.fromEntries((g.flags ?? []).map((f) => [f.id, false])),
    defeated: [], opened: [], used: [], visited: [],
    ending: null,
    morale: 0, inner: { ...(g.hero_skills ?? {}) }, skillPoints: 0, checks: {}, examined: [], questsRewarded: [],
  };
  for (const id of g.start_items ?? []) state.inventory[id] = (state.inventory[id] ?? 0) + 1;
  for (const slot of SLOTS) {
    const id = g.start_equipment?.[slot];
    if (id) {
      state.inventory[id] = (state.inventory[id] ?? 0) + 1;
      state.equipment[slot] = id;
    }
  }
  const eff = effective(state, world);
  if (world.noCombat) state.hp = state.maxHp = eff.maxHp;
  state.morale = eff.maxMorale;
  return state;
}

/** Сохранение из версии без навыков: дописываем недостающие поля. */
export function upgrade(state: GameState, world: World): GameState {
  if (state.inner && state.checks) return state;
  const fresh = newState(world);
  Object.assign(state, {
    inner: fresh.inner, skillPoints: 0, checks: {}, examined: [], questsRewarded: [], morale: effective({ ...state, inner: fresh.inner }, world).maxMorale,
  });
  return state;
}

/** Внутренний навык с бонусами вещей. */
export function skillValue(state: GameState, world: World, key: string): number {
  let bonus = 0;
  for (const slot of SLOTS) bonus += world.items.get(state.equipment[slot] ?? "")?.equip?.bonus?.skills?.[key as (typeof SKILL_KEYS)[number]] ?? 0;
  return Math.max(0, (state.inner?.[key] ?? 0) + bonus);
}

export function count(state: GameState, item: string): number {
  return state.inventory[item] ?? 0;
}

export function effective(state: GameState, world: World): Effective {
  const b = { attack: 0, defense: 0, focus: 0, hp: 0 };
  for (const slot of SLOTS) {
    const bonus = world.items.get(state.equipment[slot] ?? "")?.equip?.bonus;
    if (!bonus) continue;
    b.attack += bonus.attack ?? 0;
    b.defense += bonus.defense ?? 0;
    b.focus += bonus.focus ?? 0;
    b.hp += bonus.hp ?? 0;
  }
  const maxHp = world.noCombat ? HEALTH_BASE + skillValue(state, world, "endurance") : state.maxHp + b.hp;
  return {
    attack: Math.max(0, state.attack + b.attack),
    defense: Math.max(0, state.defense + b.defense),
    maxHp: Math.max(1, maxHp),
    maxFocus: Math.max(0, state.maxFocus + b.focus),
    maxMorale: MORALE_BASE + skillValue(state, world, "will"),
  };
}

// --- сохранение ---

const key = (gameId: string) => `game:${gameId}`;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function save(gameId: string, state: GameState): void {
  try {
    storage()?.setItem(key(gameId), JSON.stringify(state));
  } catch {
    // приватный режим или переполнение: игра продолжается без сохранения
  }
}

export function load(gameId: string): GameState | null {
  try {
    const raw = storage()?.getItem(key(gameId));
    const state = raw ? (JSON.parse(raw) as GameState) : null;
    return state?.version === 2 ? state : null;
  } catch {
    return null;
  }
}

export function clearSave(gameId: string): void {
  try {
    storage()?.removeItem(key(gameId));
  } catch {
    // ничего
  }
}
