// Справочники игры и общие типы рантайма. Правила — зеркало backend/app/engine/simulator.py.

import type {
  Character, Chest, CondAll, CondAny, CondDefeated, CondFlag, CondGold, CondItem, CondLevel, CondNot, CondSkill, CondStat,
  Dialogue, EffDamage, EffGiveGold, EffGiveItem, EffGoto, EffHeal, EffLearnSkill, EffModStat, EffSetFlag, EffTakeGold,
  EffTakeItem, EffModSkill, EffLearnWeakness, Enemy, Exit, Foe, Game, Gather, Item, Level, Location, Npc, Quest, Shop, Skill, Station, Thing, Choice, Narration,
} from "../types/game";

export type Condition = CondAll | CondAny | CondNot | CondFlag | CondItem | CondStat | CondGold | CondLevel | CondDefeated | CondSkill;
export type Effect = EffSetFlag | EffGiveItem | EffTakeItem | EffGiveGold | EffTakeGold | EffLearnSkill | EffModStat | EffModSkill | EffHeal | EffDamage | EffGoto | EffLearnWeakness;
export type MapObject = Npc | Foe | Chest | Thing | Gather | Station | Exit;
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
  readonly noCombat: boolean;
  readonly skillNames = new Map<string, { name: string; description: string }>();

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
    this.noCombat = game.profile?.combat === "none";
    for (const sk of game.inner_skills ?? []) this.skillNames.set(sk.key, { name: sk.name, description: sk.description });
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

  skillName(key: string): string {
    return this.skillNames.get(key)?.name ?? key;
  }

  itemName(id: string): string {
    return this.items.get(id)?.name ?? id;
  }
}
