// Дополнительные механики (SPEC §5.12) — зеркало соответствующих мест simulator.py.

import { DEDUCE_XP } from "./inner";
import { applyStoryEffects, gainXp } from "./effects";
import { count, type GameState } from "./state";
import type { Effect, World } from "./world";

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
  const levels = gainXp(state, DEDUCE_XP, world);
  return {
    ok: true,
    messages: [`Вывод: ${found.name}`, ...res.messages, `+${DEDUCE_XP} опыта`,
      ...(levels ? [`Новый уровень: ${state.level}. Очков навыков: ${state.skillPoints}`] : [])],
  };
}
