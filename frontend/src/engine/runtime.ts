// Контроллер игры: взаимодействие с объектами, диалоги, бои, переходы, сохранение (SPEC §5.7).
// С интерфейсом общается через GameUI: каждое окно — промис, который разрешается, когда игрок его закрыл.

import type { DialogueChoice, Ending, Shop, SkillCheck } from "../types/game";
import { chance, checkKey, checkOpen, checkTarget, checkXp, DIFFICULTY_NAME, EXAMINE_XP, healthUnit, passiveHeard, QUEST_XP, type Roll, roll } from "./inner";
import { type Battle, pyRound, REST_HEAL, rewards, startBattle } from "./tactics";
import { check, describe } from "./conditions";
import { applyStoryEffects, gainXp } from "./effects";
import { spawnFor } from "./pathfinding";
import { questChanges, questViews, type QuestView } from "./quests";
import { effective, newState, save, skillValue, upgrade, type GameState } from "./state";
import { NARRATOR, World, type Condition, type Effect, type GameEvent, type MapObject } from "./world";

// --- диалог ---------------------------------------------------------------------

export interface CheckView {
  skill: string;           // ключ навыка
  name: string;            // название навыка в этой игре
  difficulty: string;      // «сложно»
  target: number;
  value: number;
  chance: number;          // 0..1
  red: boolean;
  status: "new" | "passed" | "failed";
}

export interface ChoiceView {
  text: string;
  available: boolean;
  hint: string | null; // «Нужно: ключ от архива», «Провал — попробуйте, когда навык вырастет»
  check: CheckView | null;
}

export interface PassiveView {
  skill: string;
  name: string;
  difficulty: string;
  text: string;
}

export interface LineView {
  speaker: string; // id персонажа, "narrator" или "skill:<ключ>"
  text: string;
  emotion: string;
  passives: PassiveView[]; // голоса навыков, которые прозвучали перед репликой
  choices: ChoiceView[]; // пусто — «Далее»
}

export interface ChooseResult {
  messages: string[];
  roll: (Roll & { skill: string; name: string; red: boolean }) | null;
  over: boolean; // Здоровье или Дух на нуле
}

export interface RunnerHooks {
  random: () => number;
  /** Опыт за успешную проверку; возвращает сообщения о новом уровне. */
  reward: (xp: number) => string[];
}

/** Пошаговый проход по событию: Dialogue, Choice или Narration. */
export class DialogueRunner {
  private nodeId: string | null;
  done = false;
  goto: string | null = null;
  over = false;

  constructor(readonly event: GameEvent, private state: GameState, private world: World, private hooks: RunnerHooks | null = null) {
    this.nodeId = event.type === "dialogue" ? startNode(event, state, world) : null;
  }

  private hint(cond: unknown): string | null {
    return cond ? `Нужно: ${describe(cond as Condition, this.world)}` : null;
  }

  private checkView(dialogueId: string, nodeId: string, index: number, chk: SkillCheck): CheckView {
    const value = skillValue(this.state, this.world, chk.skill);
    const record = this.state.checks[checkKey(dialogueId, nodeId, index)];
    const target = checkTarget(chk.difficulty);
    return {
      skill: chk.skill, name: this.world.skillName(chk.skill), difficulty: DIFFICULTY_NAME[chk.difficulty], target, value,
      chance: chance(value, target), red: !!chk.red, status: !record ? "new" : record.ok ? "passed" : "failed",
    };
  }

  current(): LineView {
    const e = this.event;
    if (e.type === "narration") return { speaker: NARRATOR, text: e.text, emotion: "neutral", passives: [], choices: [] };
    if (e.type === "choice")
      return {
        speaker: NARRATOR, text: e.prompt, emotion: "neutral", passives: [],
        choices: e.options.map((o) => {
          const ok = check(o.condition as Condition, this.state, this.world);
          return { text: o.text, available: ok, hint: ok ? null : this.hint(o.condition), check: null };
        }),
      };
    const node = e.nodes.find((n) => n.id === this.nodeId)!;
    const passives = (node.passive ?? [])
      .filter((p) => passiveHeard(skillValue(this.state, this.world, p.skill), p.difficulty))
      .map((p) => ({ skill: p.skill, name: this.world.skillName(p.skill), difficulty: DIFFICULTY_NAME[p.difficulty], text: p.text }));
    return {
      speaker: node.speaker, text: node.text, emotion: node.emotion ?? "neutral", passives,
      choices: (node.choices ?? []).map((c, i) => {
        const ok = check(c.condition as Condition, this.state, this.world);
        const chk = c.check ? this.checkView(e.id, node.id, i, c.check as SkillCheck) : null;
        const open = !c.check || checkOpen(this.state.checks[checkKey(e.id, node.id, i)], c.check as SkillCheck, chk!.value);
        const hint = !ok ? this.hint(c.condition) : open ? null : c.check!.red ? "Провал. Второй попытки не будет" : "Провал — попробуйте, когда навык вырастет";
        return { text: c.text, available: ok && open, hint, check: chk };
      }),
    };
  }

  /** «Далее» на реплике без вариантов. */
  advance(): void {
    const e = this.event;
    if (e.type !== "dialogue") {
      this.done = true;
      return;
    }
    const node = e.nodes.find((n) => n.id === this.nodeId)!;
    this.moveTo(node.next ?? "end");
  }

  /** Выбор варианта: эффекты, затем проверка навыка (если есть). */
  choose(index: number): ChooseResult {
    const e = this.event;
    const none: ChooseResult = { messages: [], roll: null, over: false };
    const options = e.type === "choice" ? e.options : e.type === "dialogue" ? e.nodes.find((n) => n.id === this.nodeId)!.choices ?? [] : [];
    const option = options[index];
    if (!option || !check(option.condition as Condition, this.state, this.world)) return none;
    if (e.type === "dialogue" && !this.current().choices[index].available) return none;
    const res = applyStoryEffects(option.effects as Effect[], this.state, this.world);
    if (res.goto) {
      this.goto = res.goto;
      this.done = true;
      return { ...none, messages: res.messages };
    }
    if (e.type !== "dialogue") {
      this.done = true;
      return { ...none, messages: res.messages };
    }
    const choice = option as DialogueChoice;
    if (!choice.check) {
      this.moveTo(choice.next);
      return { ...none, messages: res.messages };
    }
    return this.resolveCheck(e.id, this.nodeId!, index, choice, res.messages);
  }

  /** Бросок 2d6 + навык (как resolve_check в simulator.py). */
  private resolveCheck(dialogueId: string, nodeId: string, index: number, choice: DialogueChoice, messages: string[]): ChooseResult {
    const chk = choice.check as SkillCheck;
    const key = checkKey(dialogueId, nodeId, index);
    if (this.state.checks[key]?.ok) {
      this.moveTo(choice.next);
      return { messages, roll: null, over: false };
    }
    const value = skillValue(this.state, this.world, chk.skill);
    const r = roll(value, checkTarget(chk.difficulty), this.hooks?.random ?? Math.random);
    this.state.checks[key] = { ok: r.success, at: value };
    const out: ChooseResult = { messages, roll: { ...r, skill: chk.skill, name: this.world.skillName(chk.skill), red: !!chk.red }, over: false };
    if (r.success) {
      messages.push(...(this.hooks?.reward(checkXp(chk.difficulty)) ?? []));
      this.moveTo(choice.next);
      return out;
    }
    if (chk.damage === "health") {
      const unit = healthUnit(effective(this.state, this.world).maxHp, this.world.noCombat);
      this.state.hp -= unit;
      messages.push(`Здоровье −${unit}`);
    } else if (chk.damage === "morale") {
      this.state.morale -= 1;
      messages.push("Дух −1");
    }
    if (this.state.hp <= 0 || this.state.morale <= 0) {
      this.state.hp = Math.max(0, this.state.hp);
      this.state.morale = Math.max(0, this.state.morale);
      this.over = out.over = true;
      this.done = true;
      return out;
    }
    this.moveTo(chk.failure);
    return out;
  }

  private moveTo(next: string): void {
    if (next === "end") this.done = true;
    else this.nodeId = next;
  }
}

/** Первая реплика диалога: первая подходящая entries, иначе start_node (как start_node в simulator.py). */
export function startNode(dialogue: Extract<GameEvent, { type: "dialogue" }>, state: GameState, world: World): string {
  for (const entry of dialogue.entries ?? []) if (check(entry.condition as Condition, state, world)) return entry.node;
  return dialogue.start_node;
}

// --- интерфейс ---------------------------------------------------------------------

export interface GameUI {
  /** Показать диалог и провести его до конца. */
  dialogue(runner: DialogueRunner, context: { npc?: string }): Promise<void>;
  battle(battle: Battle): Promise<"win" | "lose" | "fled">;
  shop(shop: Shop): Promise<void>;
  notify(messages: string[]): void;
  enterLocation(): void;
  ending(ending: Ending): void;
  gameOver(): void;
  refresh(): void;
}

// --- контроллер ------------------------------------------------------------------

export class GameController {
  readonly world: World;
  state: GameState;
  busy = false;
  private quests: QuestView[];

  constructor(game: World["game"], readonly gameId: string, readonly ui: GameUI, readonly random: () => number, saved: GameState | null) {
    this.world = new World(game, gameId);
    this.state = saved ? upgrade(saved, this.world) : newState(this.world);
    if (!saved) {
      const [floor, x] = spawnFor(this.world.level(this.state.location), null);
      Object.assign(this.state, { floor, x });
    }
    this.quests = questViews(this.state, this.world);
  }

  get location() {
    return this.world.location(this.state.location);
  }

  get level() {
    return this.world.level(this.state.location);
  }

  /** Есть ли объект на карте сейчас: условие выполнено, враг не побеждён, сундук не открыт. */
  present(obj: MapObject): boolean {
    const s = this.state;
    if (s.defeated.includes(obj.id) || s.opened.includes(obj.id)) return false;
    if (obj.type === "thing" && (obj.once ?? true) && s.used.includes(obj.id)) return false;
    return check(obj.condition as Condition, s, this.world);
  }

  companionPresent(): boolean {
    const c = this.world.companion();
    return !!c && check(c.joins as Condition, this.state, this.world);
  }

  exitOpen(obj: MapObject): boolean {
    return obj.type !== "exit" || check(obj.requires as Condition, this.state, this.world);
  }

  /** Первый вход в игру: сценка стартовой локации. */
  async start(): Promise<void> {
    this.ui.enterLocation();
    if (!this.state.visited.includes(this.state.location)) await this.arrive();
    this.after();
  }

  async interact(obj: MapObject): Promise<"fled" | void> {
    if (this.busy || !this.present(obj)) return;
    this.busy = true;
    try {
      let jump: string | null = null;
      if (obj.type === "npc") {
        jump = await this.run(obj.dialogue as GameEvent, { npc: obj.character });
        if (!jump && obj.shop) {
          this.after();
          await this.ui.shop(this.world.shops.get(obj.shop)!);
        }
      } else if (obj.type === "thing") {
        if (obj.once ?? true) this.state.used.push(obj.id);
        if (!this.state.examined.includes(obj.id)) {
          this.state.examined.push(obj.id);
          this.ui.notify(this.reward(EXAMINE_XP));
        }
        jump = await this.run(obj.event as GameEvent, {});
      } else if (obj.type === "chest") {
        if (!check(obj.requires as Condition, this.state, this.world)) {
          await this.narrate(this.locked(obj.locked_text, obj.requires));
        } else {
          this.state.opened.push(obj.id);
          const res = applyStoryEffects(obj.contents as Effect[], this.state, this.world);
          this.ui.notify(res.messages.length ? res.messages : ["Пусто."]);
          jump = res.goto;
        }
      } else if (obj.type === "exit") {
        if (!check(obj.requires as Condition, this.state, this.world)) await this.narrate(this.locked(obj.locked_text, obj.requires));
        else jump = obj.to;
      } else if (obj.type === "enemy") {
        const outcome = await this.fight(obj);
        if (outcome === "fled" || outcome === "over") {
          this.after();
          return outcome === "fled" ? "fled" : undefined;
        }
        jump = outcome;
      }
      this.after();
      if (jump) await this.go(jump);
    } finally {
      this.busy = false;
    }
  }

  private locked(text: string | null | undefined, cond: unknown): string {
    const hint = cond ? `[Нужно: ${describe(cond as Condition, this.world)}]` : "";
    return [text ?? "Заперто.", hint].filter(Boolean).join(" ");
  }

  private async narrate(text: string): Promise<void> {
    await this.ui.dialogue(new DialogueRunner({ type: "narration", id: "_", text }, this.state, this.world), {});
  }

  private async run(event: GameEvent, context: { npc?: string }): Promise<string | null> {
    if (!check(event.condition as Condition, this.state, this.world)) return null;
    const runner = new DialogueRunner(event, this.state, this.world, { random: this.random, reward: (xp) => this.reward(xp) });
    await this.ui.dialogue(runner, context);
    if (runner.over) {
      save(this.gameId, this.state);
      this.ui.gameOver();
      return null;
    }
    return runner.goto;
  }

  /** Опыт не за бой (§5.10): проверки, осмотры, квесты. Возвращает сообщения о новом уровне и очках навыков. */
  reward(xp: number): string[] {
    const levels = gainXp(this.state, xp, this.world);
    return levels ? [`Новый уровень: ${this.state.level}. Очков навыков: ${this.state.skillPoints}`] : [];
  }

  /** Бой; возвращает цель goto, "fled" или "over" (поражение / конец). */
  private async fight(obj: Extract<MapObject, { type: "enemy" }>): Promise<string | null | "fled" | "over"> {
    const battle = startBattle(obj, this.state, this.world, this.random);
    const result = await this.ui.battle(battle);
    const hero = battle.hero();
    this.state.hp = Math.max(result === "lose" ? 0 : 1, hero.hp);
    if (result === "win") this.state.hp = Math.min(hero.maxHp, this.state.hp + pyRound(hero.maxHp * REST_HEAL));
    if (result === "fled") return "fled";
    if (result === "win") {
      this.state.defeated.push(obj.id);
      const { xp, gold } = rewards(obj, this.world);
      this.state.gold += gold;
      const levels = this.reward(xp);
      const res = applyStoryEffects(obj.on_win as Effect[], this.state, this.world);
      this.ui.notify([`Победа! +${xp} опыта, +${gold} золота`, ...levels, ...res.messages]);
      return res.goto;
    }
    if (obj.on_lose === "game_over" || obj.on_lose === undefined) {
      this.ui.gameOver();
      return "over";
    }
    this.state.hp = 1;
    const res = applyStoryEffects(obj.on_lose as Effect[], this.state, this.world);
    this.ui.notify(["Поражение… но история продолжается.", ...res.messages]);
    return res.goto;
  }

  /** Переход в локацию или на концовку. */
  async go(target: string): Promise<void> {
    if (this.world.endings.has(target)) {
      this.state.ending = target;
      save(this.gameId, this.state);
      this.ui.ending(this.world.game.endings.find((e) => e.id === target)!);
      return;
    }
    this.state.cameFrom = this.state.location;
    this.state.location = target;
    const [floor, x] = spawnFor(this.world.level(target), this.state.cameFrom);
    Object.assign(this.state, { floor, x });
    this.ui.enterLocation();
    if (!this.state.visited.includes(target)) await this.arrive();
    this.after();
  }

  /** Первый вход в локацию: вступление и сценки on_enter. */
  private async arrive(): Promise<void> {
    const loc = this.location;
    this.state.visited.push(loc.id);
    await this.narrate(loc.intro);
    for (const event of (loc.on_enter ?? []) as GameEvent[]) {
      const jump = await this.run(event, {});
      if (jump) {
        this.after();
        await this.go(jump);
        return;
      }
    }
  }

  /** После каждого действия: изменения в журнале, сохранение, перерисовка HUD. */
  after(): void {
    const now = questViews(this.state, this.world);
    const changes = questChanges(this.quests, now);
    this.quests = now;
    for (const v of now) {
      if (v.complete && !this.state.questsRewarded.includes(v.quest.id)) {
        this.state.questsRewarded.push(v.quest.id);
        changes.push(...this.reward(QUEST_XP));
      }
    }
    if (changes.length) this.ui.notify(changes);
    save(this.gameId, this.state);
    this.ui.refresh();
  }

  questViews(): QuestView[] {
    return this.quests;
  }
}
