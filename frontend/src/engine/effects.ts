// Эффекты вне боя, опыт, экипировка и торговля. Зеркало simulator.py.

import { count, effective, type GameState } from "./state";
import { SLOTS, type Effect, type Slot, type World } from "./world";

export interface EffectResult {
  goto: string | null;
  messages: string[]; // для ленты: «Получено: Ключ от архива»
}

/** Применяет эффекты по порядку; goto прерывает список (SPEC §5.5, NOTES). */
export function applyStoryEffects(effects: Effect[] | undefined, state: GameState, world: World): EffectResult {
  const messages: string[] = [];
  for (const e of effects ?? []) {
    if ("goto" in e) return { goto: e.goto, messages };
    const msg = applyHeroEffect(e, state, world);
    if (msg) messages.push(msg);
  }
  return { goto: null, messages };
}

export function applyHeroEffect(e: Effect, state: GameState, world: World): string | null {
  const eff = effective(state, world);
  if ("set_flag" in e) {
    state.flags[e.set_flag] = e.value;
    return null;
  }
  if ("give_item" in e) {
    state.inventory[e.give_item] = count(state, e.give_item) + 1;
    return `Получено: ${world.itemName(e.give_item)}`;
  }
  if ("take_item" in e) {
    if (count(state, e.take_item) > 0) {
      state.inventory[e.take_item] -= 1;
      if (state.inventory[e.take_item] === 0) {
        delete state.inventory[e.take_item];
        for (const slot of SLOTS) if (state.equipment[slot] === e.take_item) delete state.equipment[slot];
      }
      return `Отдано: ${world.itemName(e.take_item)}`;
    }
    return null;
  }
  if ("give_gold" in e) {
    state.gold += e.give_gold;
    return `+${e.give_gold} золота`;
  }
  if ("take_gold" in e) {
    state.gold = Math.max(0, state.gold - e.take_gold);
    return `−${e.take_gold} золота`;
  }
  if ("learn_skill" in e) {
    if (state.skills.includes(e.learn_skill)) return null;
    state.skills.push(e.learn_skill);
    return `Новый навык: ${world.skills.get(e.learn_skill)?.name ?? e.learn_skill}`;
  }
  if ("heal" in e) {
    const before = state.hp;
    state.hp = Math.min(eff.maxHp, state.hp + e.heal);
    return state.hp > before ? `Здоровье +${state.hp - before}` : null;
  }
  if ("damage" in e) {
    state.hp = Math.max(1, state.hp - e.damage); // вне боя урон не убивает
    return `Здоровье −${e.damage}`;
  }
  if ("mod_stat" in e) {
    if (e.mod_stat === "hp") {
      state.maxHp = Math.max(1, state.maxHp + e.delta);
      state.hp = Math.max(1, Math.min(effective(state, world).maxHp, state.hp + e.delta));
    } else if (e.mod_stat === "focus") {
      state.maxFocus = Math.max(0, state.maxFocus + e.delta);
      state.focus = Math.max(0, Math.min(effective(state, world).maxFocus, state.focus + e.delta));
    } else {
      state[e.mod_stat] = Math.max(0, state[e.mod_stat] + e.delta);
    }
    const names = { hp: "Здоровье", attack: "Атака", defense: "Защита", focus: "Фокус" };
    return `${names[e.mod_stat]} ${e.delta >= 0 ? "+" : "−"}${Math.abs(e.delta)}`;
  }
  return null;
}

/** Опыт; на новом уровне — прирост статов и полное восстановление. Возвращает число полученных уровней. */
export function gainXp(state: GameState, xp: number, world: World): number {
  state.xp += xp;
  const prog = world.game.progression!;
  let gained = 0;
  while (state.level - 1 < prog.xp_to_level.length && state.xp >= prog.xp_to_level[state.level - 1]) {
    state.level += 1;
    gained += 1;
    state.maxHp += prog.per_level.hp;
    state.attack += prog.per_level.attack;
    state.defense += prog.per_level.defense;
    state.maxFocus += prog.per_level.focus;
    const eff = effective(state, world);
    state.hp = eff.maxHp;
    state.focus = eff.maxFocus;
  }
  return gained;
}

export function nextLevelXp(state: GameState, world: World): number | null {
  return world.game.progression!.xp_to_level[state.level - 1] ?? null;
}

// --- экипировка ---

export function equip(state: GameState, world: World, itemId: string): void {
  const item = world.items.get(itemId);
  if (!item?.equip || count(state, itemId) === 0) return;
  state.equipment[item.equip.slot as Slot] = itemId;
  state.hp = Math.min(state.hp, effective(state, world).maxHp);
}

export function unequip(state: GameState, world: World, slot: Slot): void {
  delete state.equipment[slot];
  const eff = effective(state, world);
  state.hp = Math.min(state.hp, eff.maxHp);
  state.focus = Math.min(state.focus, eff.maxFocus);
}

export function isEquipped(state: GameState, itemId: string): boolean {
  return SLOTS.some((s) => state.equipment[s] === itemId);
}

/** Расходуемый предмет вне боя: эффекты применяются к герою. */
export function useItem(state: GameState, world: World, itemId: string): string[] {
  const item = world.items.get(itemId);
  if (!item || item.kind !== "consumable" || count(state, itemId) === 0) return [];
  state.inventory[itemId] -= 1;
  if (state.inventory[itemId] === 0) delete state.inventory[itemId];
  return (item.effect ?? []).map((e) => applyHeroEffect(e as Effect, state, world)).filter((m): m is string => !!m);
}

// --- торговля ---

export const SELL_RATE = 0.5;

export function sellPrice(world: World, itemId: string): number {
  return Math.floor((world.items.get(itemId)?.price ?? 0) * SELL_RATE);
}

export function buy(state: GameState, world: World, itemId: string): boolean {
  const price = world.items.get(itemId)?.price ?? 0;
  if (state.gold < price) return false;
  state.gold -= price;
  state.inventory[itemId] = count(state, itemId) + 1;
  return true;
}

export function canSell(state: GameState, world: World, itemId: string): boolean {
  const item = world.items.get(itemId);
  // ключи и сюжетные предметы не продаются: на них держатся двери, условия и концовки
  if (!item || item.kind === "key" || item.kind === "misc" || count(state, itemId) === 0) return false;
  return !(isEquipped(state, itemId) && count(state, itemId) === 1);
}

export function sell(state: GameState, world: World, itemId: string): boolean {
  if (!canSell(state, world, itemId)) return false;
  state.gold += sellPrice(world, itemId);
  state.inventory[itemId] -= 1;
  if (state.inventory[itemId] === 0) delete state.inventory[itemId];
  return true;
}
