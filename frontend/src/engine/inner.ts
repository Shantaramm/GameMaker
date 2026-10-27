// Внутренние навыки и проверки в разговоре (SPEC §5.10) — зеркало backend/app/engine/inner.py.
// Проверка: 2d6 + навык против сложности; 6-6 — всегда успех, 1-1 — всегда провал.
// Пассивная проверка — без броска: навык + 6 ≥ сложности.

import type { SkillCheck } from "../types/game";

export type Difficulty = SkillCheck["difficulty"];
export const SKILL_KEYS = ["logic", "knowledge", "empathy", "will", "endurance", "presence", "perception", "finesse"] as const;
export type SkillKey = (typeof SKILL_KEYS)[number];
export const SKILL_GROUPS: [string, SkillKey[]][] = [
  ["Ум", ["logic", "knowledge"]], ["Психика", ["empathy", "will"]], ["Тело", ["endurance", "presence"]], ["Чувства", ["perception", "finesse"]],
];

export const DIFFICULTY_TARGET: Record<Difficulty, number> = { trivial: 6, easy: 8, medium: 10, challenging: 12, formidable: 14, legendary: 16 };
const STEPS: Difficulty[] = ["trivial", "easy", "medium", "challenging", "formidable", "legendary"];
export const DIFFICULTY_NAME: Record<Difficulty, string> = {
  trivial: "элементарно", easy: "легко", medium: "средне", challenging: "сложно", formidable: "очень сложно", legendary: "легендарно",
};
export const PASSIVE_BONUS = 6;
export const SKILL_CAP = 6;
export const MOD_SKILL_CAP = 8;
export const CHECK_XP_BASE = 5;
export const CHECK_XP_STEP = 2;
export const EXAMINE_XP = 3;
export const QUEST_XP = 20;
export const HEALTH_UNIT_SHARE = 6;
export const HEALTH_BASE = 3;
export const MORALE_BASE = 3;

export const checkTarget = (d: Difficulty) => DIFFICULTY_TARGET[d];
export const checkXp = (d: Difficulty) => CHECK_XP_BASE + CHECK_XP_STEP * STEPS.indexOf(d);

function success(a: number, b: number, value: number, target: number): boolean {
  if (a === 6 && b === 6) return true;
  if (a === 1 && b === 1) return false;
  return a + b + value >= target;
}

export function chance(value: number, target: number): number {
  let ok = 0;
  for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) if (success(a, b, value, target)) ok++;
  return ok / 36;
}

export interface Roll { dice: [number, number]; value: number; target: number; success: boolean }

export function roll(value: number, target: number, random: () => number): Roll {
  const a = 1 + Math.floor(random() * 6);
  const b = 1 + Math.floor(random() * 6);
  return { dice: [a, b], value, target, success: success(a, b, value, target) };
}

export const passiveHeard = (value: number, d: Difficulty) => value + PASSIVE_BONUS >= checkTarget(d);
export const checkKey = (dialogueId: string, nodeId: string, index: number) => `${dialogueId}:${nodeId}:${index}`;

export interface CheckRecord { ok: boolean; at: number }

/** Можно ли выбрать вариант с проверкой: белая после провала — когда навык вырос, красная — никогда. */
export function checkOpen(record: CheckRecord | undefined, check: SkillCheck, value: number): boolean {
  if (!record || record.ok) return true;
  return !check.red && value > record.at;
}

export const healthUnit = (maxHp: number, noCombat: boolean) => (noCombat ? 1 : Math.max(1, Math.round(maxHp / HEALTH_UNIT_SHARE)));
