// Условия (SPEC §5.5) и их человекочитаемые подсказки для серых вариантов.

import { count, effective, type GameState, skillValue } from "./state";
import type { Condition, World } from "./world";

export function check(cond: Condition | null | undefined, state: GameState, world: World): boolean {
  if (!cond) return true;
  if ("all" in cond) return cond.all.every((c) => check(c, state, world));
  if ("any" in cond) return cond.any.some((c) => check(c, state, world));
  if ("not" in cond) return !check(cond.not, state, world);
  if ("flag" in cond) return (state.flags[cond.flag] ?? false) === cond.is;
  if ("has_item" in cond) return count(state, cond.has_item) > 0;
  if ("defeated" in cond) return state.defeated.includes(cond.defeated);
  let value: number;
  let op: ">=" | "<=";
  if ("skill" in cond) {
    value = skillValue(state, world, cond.skill);
    op = cond.op;
  } else if ("stat" in cond) {
    const eff = effective(state, world);
    value = { hp: state.hp, focus: state.focus, attack: eff.attack, defense: eff.defense, morale: state.morale }[cond.stat];
    op = cond.op;
  } else if ("gold" in cond) {
    value = state.gold;
    op = cond.gold;
  } else {
    value = state.level;
    op = cond.level;
  }
  return op === ">=" ? value >= cond.value : value <= cond.value;
}

const STAT_NAMES = { hp: "здоровье", attack: "атака", defense: "защита", focus: "фокус", morale: "дух" };

/** «ключ от архива», «уровень 3», «победить: Служитель тумана, Морская тень»… */
export function describe(cond: Condition, world: World): string {
  if ("all" in cond) return cond.all.map((c) => describe(c, world)).join(", ");
  if ("any" in cond) return cond.any.map((c) => describe(c, world)).join(" или ");
  if ("not" in cond) return `не ${describe(cond.not, world)}`;
  if ("flag" in cond) {
    const name = world.flagNames.get(cond.flag) ?? cond.flag;
    return cond.is ? name : `не: ${name}`;
  }
  if ("has_item" in cond) return world.itemName(cond.has_item);
  if ("defeated" in cond) {
    const foe = world.foes.get(cond.defeated);
    const names = foe ? foe.enemies.map((id) => world.enemies.get(id)?.name ?? id) : [cond.defeated];
    return `победить: ${[...new Set(names)].join(", ")}`;
  }
  if ("gold" in cond) return cond.gold === ">=" ? `${cond.value} золота` : `не больше ${cond.value} золота`;
  if ("level" in cond) return cond.level === ">=" ? `уровень ${cond.value}` : `уровень не выше ${cond.value}`;
  if ("skill" in cond) return `${world.skillName(cond.skill)} ${cond.op === ">=" ? "≥" : "≤"} ${cond.value}`;
  return `${STAT_NAMES[cond.stat]} ${cond.op === ">=" ? "≥" : "≤"} ${cond.value}`;
}
