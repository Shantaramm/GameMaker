// Справочники игры и общие типы рантайма. Правила — зеркало backend/app/engine/simulator.py.

import type {
  Character, Chest, CondAll, CondAny, CondDefeated, CondFlag, CondGold, CondItem, CondLevel, CondNot, CondStat,
  Dialogue, EffDamage, EffGiveGold, EffGiveItem, EffGoto, EffHeal, EffLearnSkill, EffModStat, EffSetFlag, EffTakeGold,
  EffTakeItem, Enemy, Exit, Foe, Game, Item, Level, Location, Npc, Quest, Shop, Skill, Thing, Choice, Narration,
} from "../types/game";

export type Condition = CondAll | CondAny | CondNot | CondFlag | CondItem | CondStat | CondGold | CondLevel | CondDefeated;
export type Effect = EffSetFlag | EffGiveItem | EffTakeItem | EffGiveGold | EffTakeGold | EffLearnSkill | EffModStat | EffHeal | EffDamage | EffGoto;
export type MapObject = Npc | Foe | Chest | Thing | Exit;
export type GameEvent = Dialogue | Choice | Narration;
export type Slot = "hand" | "body" | "trinket";
export const SLOTS: Slot[] = ["hand", "body", "trinket"];
export const NARRATOR = "narrator";

export class World {
  readonly items = new Map<string, Item>();
  readonly skills = new Map<string, Skill>();
  readonly enemies = new Map<string, Enemy>();
  readonly shops = new Map<string, Shop>();
  readonly characters = new Map<string, Character>();
  readonly locations = new Map<string, Location>();
  readonly flagNames = new Map<string, string>();
  readonly endings: Set<string>;
  readonly foes = new Map<string, Foe>();

  constructor(readonly game: Game, readonly id: string) {
    for (const i of game.items ?? []) this.items.set(i.id, i);
    for (const k of game.skills ?? []) this.skills.set(k.id, k);
    for (const e of game.enemies ?? []) this.enemies.set(e.id, e);
    for (const s of game.shops ?? []) this.shops.set(s.id, s);
    for (const c of [game.hero, ...(game.characters ?? [])]) this.characters.set(c.id, c);
    for (const l of game.locations) {
      this.locations.set(l.id, l);
      for (const o of l.objects ?? []) if (o.type === "enemy") this.foes.set(o.id, o);
    }
    for (const f of game.flags ?? []) this.flagNames.set(f.id, f.description ?? f.id);
    this.endings = new Set(game.endings.map((e) => e.id));
    if (!game.stats_template || !game.progression || !game.levels) throw new Error("игра не собрана: нет баланса или уровней");
  }

  location(id: string): Location {
    return this.locations.get(id)!;
  }

  level(id: string): Level {
    return this.game.levels![id];
  }

  get quests(): Quest[] {
    return this.game.quests ?? [];
  }

  companion(): Character | undefined {
    return (this.game.characters ?? []).find((c) => c.role === "companion");
  }

  itemName(id: string): string {
    return this.items.get(id)?.name ?? id;
  }
}
