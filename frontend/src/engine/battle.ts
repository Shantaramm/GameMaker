// Пошаговый бой (SPEC §5.7). Правила совпадают с run_battle в simulator.py:
// инициатива у героя; урон max(1, attack − defense/2) ± 20%; фокус восполняется в начале боя и +1 за ход;
// способность врага срабатывает вместо атаки, если номер его хода делится на every_n_turns;
// бафы навыков действуют до конца боя; побег — 50%, если can_flee.

import type { EnemyAbility } from "../types/game";
import { applyHeroEffect } from "./effects";
import { count, effective, type GameState } from "./state";
import type { Effect, MapObject, World } from "./world";

type Foe = Extract<MapObject, { type: "enemy" }>;

export const DAMAGE_SPREAD = 0.2;
export const FLEE_CHANCE = 0.5;
export const FOCUS_REGEN_PER_TURN = 1;

export interface Fighter {
  enemyId: string;
  name: string;
  hp: number;
  maxHp: number;
  attack: number;
  defense: number;
  abilities: EnemyAbility[];
  turn: number;
}

export type Actor = "hero" | number; // number — индекс врага

export interface BattleEvent {
  actor: Actor;
  target: Actor | null;
  amount: number;          // урон (>0) или лечение (<0)
  text: string;
}

export function rollDamage(attack: number, defense: number, random: () => number): number {
  const base = Math.max(1, attack - Math.floor(defense / 2));
  return Math.max(1, Math.round(base * (1 - DAMAGE_SPREAD + random() * 2 * DAMAGE_SPREAD)));
}

export class Battle {
  readonly foes: Fighter[];
  readonly buff = { attack: 0, defense: 0 };
  result: "win" | "lose" | "fled" | null = null;

  constructor(readonly foe: Foe, readonly state: GameState, readonly world: World, readonly random: () => number) {
    this.foes = foe.enemies.map((id) => {
      const e = world.enemies.get(id)!;
      return { enemyId: id, name: e.name, hp: e.hp!, maxHp: e.hp!, attack: e.attack!, defense: e.defense!, abilities: e.abilities ?? [], turn: 0 };
    });
    state.focus = effective(state, world).maxFocus;
  }

  get alive(): number[] {
    return this.foes.map((f, i) => (f.hp > 0 ? i : -1)).filter((i) => i >= 0);
  }

  private target(index: number): number {
    return this.foes[index]?.hp > 0 ? index : this.alive[0];
  }

  private hit(t: number, effects: Effect[], who: string, events: BattleEvent[]): void {
    const foe = this.foes[t];
    for (const e of effects) {
      if ("damage" in e) {
        foe.hp -= e.damage;
        events.push({ actor: "hero", target: t, amount: e.damage, text: `${who}: ${foe.name} −${e.damage}` });
      } else if ("mod_stat" in e && (e.mod_stat === "attack" || e.mod_stat === "defense")) {
        foe[e.mod_stat] = Math.max(0, foe[e.mod_stat] + e.delta);
        events.push({ actor: "hero", target: t, amount: 0, text: `${foe.name}: ${e.mod_stat === "attack" ? "атака" : "защита"} ${e.delta >= 0 ? "+" : "−"}${Math.abs(e.delta)}` });
      }
    }
  }

  /** Бой окончен или бить некого: действия героя игнорируются (защита от лишнего тапа во время анимации). */
  private get over(): boolean {
    return this.result !== null || !this.alive.length;
  }

  attack(index: number): BattleEvent[] {
    if (this.over) return [];
    const t = this.target(index);
    const foe = this.foes[t];
    const dmg = rollDamage(effective(this.state, this.world).attack + this.buff.attack, foe.defense, this.random);
    foe.hp -= dmg;
    return this.endTurn([{ actor: "hero", target: t, amount: dmg, text: `Удар: ${foe.name} −${dmg}` }]);
  }

  canUseSkill(skillId: string): boolean {
    const skill = this.world.skills.get(skillId);
    return !!skill && this.state.skills.includes(skillId) && this.state.focus >= skill.cost_focus;
  }

  skill(skillId: string, index: number): BattleEvent[] {
    const skill = this.world.skills.get(skillId)!;
    if (this.over || !this.canUseSkill(skillId)) return [];
    this.state.focus -= skill.cost_focus;
    const events: BattleEvent[] = [];
    if (skill.target === "enemy") this.hit(this.target(index), skill.effect as Effect[], skill.name, events);
    else
      for (const e of skill.effect as Effect[]) {
        if ("mod_stat" in e && (e.mod_stat === "attack" || e.mod_stat === "defense")) {
          this.buff[e.mod_stat] += e.delta;
          events.push({ actor: "hero", target: "hero", amount: 0, text: `${skill.name}: ${e.mod_stat === "attack" ? "атака" : "защита"} +${e.delta} до конца боя` });
        } else {
          const before = this.state.hp;
          const msg = applyHeroEffect(e, this.state, this.world);
          events.push({ actor: "hero", target: "hero", amount: before - this.state.hp, text: `${skill.name}: ${msg ?? ""}` });
        }
      }
    return this.endTurn(events);
  }

  item(itemId: string, index: number): BattleEvent[] {
    const item = this.world.items.get(itemId);
    if (this.over || !item || item.kind !== "consumable" || count(this.state, itemId) === 0) return [];
    this.state.inventory[itemId] -= 1;
    if (this.state.inventory[itemId] === 0) delete this.state.inventory[itemId];
    const events: BattleEvent[] = [];
    for (const e of (item.effect ?? []) as Effect[]) {
      if ("damage" in e) this.hit(this.target(index), [e], item.name, events);
      else {
        const before = this.state.hp;
        const msg = applyHeroEffect(e, this.state, this.world);
        events.push({ actor: "hero", target: "hero", amount: before - this.state.hp, text: `${item.name}: ${msg ?? ""}` });
      }
    }
    return this.endTurn(events);
  }

  flee(): BattleEvent[] {
    if (this.over) return [];
    if (this.foe.can_flee && this.random() < FLEE_CHANCE) {
      this.result = "fled";
      return [{ actor: "hero", target: null, amount: 0, text: "Удалось сбежать!" }];
    }
    return this.endTurn([{ actor: "hero", target: null, amount: 0, text: this.foe.can_flee ? "Сбежать не вышло." : "Отсюда не сбежать." }]);
  }

  private endTurn(events: BattleEvent[]): BattleEvent[] {
    if (!this.alive.length) {
      this.result = "win";
      return events;
    }
    const eff = effective(this.state, this.world);
    for (const i of this.alive) {
      const f = this.foes[i];
      f.turn += 1;
      const ability = f.abilities.find((a) => f.turn % a.every_n_turns === 0);
      if (ability) {
        for (const e of ability.effect as Effect[]) {
          if ("damage" in e) {
            this.state.hp -= e.damage;
            events.push({ actor: i, target: "hero", amount: e.damage, text: `${f.name} — ${ability.name}: −${e.damage}` });
          } else if ("heal" in e) {
            f.hp = Math.min(f.maxHp, f.hp + e.heal);
            events.push({ actor: i, target: i, amount: -e.heal, text: `${f.name} — ${ability.name}: +${e.heal}` });
          } else if ("mod_stat" in e && (e.mod_stat === "attack" || e.mod_stat === "defense")) {
            f[e.mod_stat] = Math.max(0, f[e.mod_stat] + e.delta);
            events.push({ actor: i, target: i, amount: 0, text: `${f.name} — ${ability.name}` });
          }
        }
      } else {
        const dmg = rollDamage(f.attack, eff.defense + this.buff.defense, this.random);
        this.state.hp -= dmg;
        events.push({ actor: i, target: "hero", amount: dmg, text: `${f.name} бьёт: −${dmg}` });
      }
      if (this.state.hp <= 0) {
        this.state.hp = 0;
        this.result = "lose";
        return events;
      }
    }
    this.state.focus = Math.min(eff.maxFocus, this.state.focus + FOCUS_REGEN_PER_TURN);
    return events;
  }

  rewards(): { xp: number; gold: number } {
    const enemies = this.foe.enemies.map((id) => this.world.enemies.get(id)!);
    return { xp: enemies.reduce((s, e) => s + (e.xp ?? 0), 0), gold: enemies.reduce((s, e) => s + (e.gold ?? 0), 0) };
  }
}
