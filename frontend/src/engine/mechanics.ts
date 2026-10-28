// Дополнительные механики (SPEC §5.12) — зеркало соответствующих мест simulator.py.

import type { Gather, Recipe } from "../types/game";
import { CRAFT_XP, DEDUCE_XP, GATHER_BONUS, passiveHeard } from "./inner";
import { applyStoryEffects, gainXp } from "./effects";
import { count, type GameState, skillValue } from "./state";
import type { Effect, World } from "./world";

function levelUp(state: GameState, world: World, xp: number): string[] {
  return gainXp(state, xp, world) ? [`Новый уровень: ${state.level}. Очков навыков: ${state.skillPoints}`] : [];
}

export interface MechanicResult {
  ok: boolean;
  messages: string[];
}

// --- улики и выводы ---

/** Улики героя (предметы kind=clue). */
export function clues(state: GameState, world: World): string[] {
  return Object.keys(state.inventory).filter((id) => count(state, id) > 0 && world.items.get(id)?.kind === "clue");
}

/** Соединить улики на доске: совпали с выводом — озарение, эффекты и опыт; нет — «не складывается» и −1 Дух (не ниже 1). */
export function deduce(state: GameState, world: World, picked: string[]): MechanicResult {
  const set = new Set(picked);
  const found = (world.game.deductions ?? []).find((d) => d.clues.length === set.size && d.clues.every((c) => set.has(c)));
  if (!found) {
    const messages = ["Не складывается."];
    if (state.morale > 1) {
      state.morale -= 1;
      messages.push("Дух −1");
    }
    return { ok: false, messages };
  }
  if (state.deduced.includes(found.id)) return { ok: false, messages: ["Этот вывод уже сделан."] };
  state.deduced.push(found.id);
  const res = applyStoryEffects(found.effects as Effect[], state, world);
  return { ok: true, messages: [`Вывод: ${found.name}`, ...res.messages, `+${DEDUCE_XP} опыта`, ...levelUp(state, world, DEDUCE_XP)] };
}

// --- сбор и ремесло ---

export const STATION_NAMES: Record<string, string> = { anywhere: "из сумки", workbench: "верстак", alchemy: "котёл", campfire: "костёр" };

/** Сколько даёт место сбора: amount и +1, если навык высок (как gather_amount в simulator.py). */
export function gatherAmount(obj: Gather, state: GameState, world: World): number {
  const bonus = !!obj.skill && passiveHeard(skillValue(state, world, obj.skill), GATHER_BONUS);
  return (obj.amount ?? 1) + (bonus ? 1 : 0);
}

export function recipesAt(world: World, station: string): Recipe[] {
  return (world.game.recipes ?? []).filter((r) => (r.station ?? "anywhere") === station || (r.station ?? "anywhere") === "anywhere");
}

export function canCraft(recipe: Recipe, state: GameState): boolean {
  return recipe.inputs.every((i) => count(state, i.item) >= (i.count ?? 1));
}

/** Сделать вещь по рецепту: сырьё уходит, результат в сумку; впервые по этому рецепту — опыт. */
export function craft(state: GameState, world: World, recipe: Recipe): MechanicResult {
  if (!canCraft(recipe, state)) return { ok: false, messages: ["Не хватает сырья."] };
  for (const i of recipe.inputs) {
    state.inventory[i.item] -= i.count ?? 1;
    if (state.inventory[i.item] <= 0) delete state.inventory[i.item];
  }
  const amount = recipe.amount ?? 1;
  state.inventory[recipe.result] = count(state, recipe.result) + amount;
  const messages = [`Сделано: ${world.itemName(recipe.result)}${amount > 1 ? ` ×${amount}` : ""}`];
  if (!state.crafted.includes(recipe.id)) {
    state.crafted.push(recipe.id);
    messages.push(`+${CRAFT_XP} опыта`, ...levelUp(state, world, CRAFT_XP));
  }
  return { ok: true, messages };
}
