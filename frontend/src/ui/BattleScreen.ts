// Экран тактического боя (SPEC §5.9): изометрическое поле, выбор бойца, клетки хода и атаки,
// предпросмотр урона с учётом фланга/спины/высоты, навыки, предметы, тактики за кураж и золото,
// пошаговый показ хода врагов. Правила — в engine/tactics.ts, здесь только интерфейс.

import { describe } from "../engine/conditions";
import type { GameState } from "../engine/state";
import {
  alive, type Battle, type BattleEvent, type Cell, manhattan, MAX_POINTS, SKILL_RANGE, stat, takeItem, type Unit,
} from "../engine/tactics";
import type { Condition, Effect, World } from "../engine/world";
import { backgroundSeed, renderBackground } from "../pixel/background";
import { library } from "../pixel/library";
import { creatureCanvas, creatureMapFrames, portraitCanvas } from "../pixel/sprite";
import { iconCanvas } from "../pixel/tiles";
import { walkerFrames } from "../pixel/walker";
import type { Item, Location, Skill, Tactic } from "../types/game";
import { type Highlight, type IsoUnit, IsoView } from "../world/iso";
import { bar, button, el, pixel, sleep } from "./dom";

type Mode =
  | { kind: "idle" }
  | { kind: "menu"; menu: "skills" | "items" | "tactics" }
  | { kind: "skill"; skill: Skill }
  | { kind: "item"; item: Item };
type Result = "win" | "lose" | "fled";

const key = (c: Cell) => `${c[0]},${c[1]}`;
const STEP_MS = 140;
const SIDE_TEXT = { front: "", flank: "фланг", back: "в спину" };
const damageOf = (effects: Effect[] | undefined) => (effects ?? []).reduce((s, e) => s + ("damage" in e ? e.damage : 0), 0);

export class BattleScreen {
  readonly root = el("div", { className: "battle hidden" });

  constructor(private world: World) {}

  open(battle: Battle, location: Location, state: GameState): Promise<Result> {
    const world = this.world;
    const take = takeItem(state);
    const view = new IsoView(battle.arena, location.theme, location.background);
    const bg = pixel(renderBackground({ ...location.background, props: [] }, backgroundSeed(world.id, location.id)).toCanvas(), 1, "pixel battle-bg");
    const floaters = el("div", { className: "battle-floaters" });
    const banner = (text: string, cls: string) => {
      const n = el("div", { className: `turn-banner ${cls}`, textContent: text });
      floaters.append(n);
      setTimeout(() => n.remove(), 1300);
    };
    const stage = el("div", { className: "battle-stage" }, view.canvas, floaters);
    const head = el("div", { className: "battle-head" });
    const card = el("div", { className: "battle-card" });
    const actions = el("div", { className: "battle-actions" });
    const log = el("div", { className: "battle-log" });
    const panel = el("div", { className: "battle-panel" }, card, el("div", { className: "battle-side" }, actions, log));
    this.root.replaceChildren(bg, head, stage, panel);
    this.root.classList.remove("hidden");

    // --- отображаемые бойцы: позиции и HP догоняют движок по мере анимации ---
    const flipFor = (facing: Cell, prev: boolean) => {
      const sx = facing[0] - facing[1];
      return sx < 0 ? true : sx > 0 ? false : prev;
    };
    const spriteOf = (u: Unit): { frames: HTMLCanvasElement[]; anchor: [number, number] } => {
      const ch = world.characters.get(u.look);
      if (ch) return { frames: walkerFrames(ch.appearance, ch.id).idle, anchor: library.layout.walker.ref };
      const e = world.enemies.get(u.look)!;
      if ("body" in e.appearance) return { frames: creatureMapFrames(e.appearance, e.id), anchor: [16, 31] };
      return { frames: walkerFrames(e.appearance, e.id).idle, anchor: library.layout.walker.ref };
    };
    const everyone = () => [...battle.party, ...battle.enemies];
    const display = new Map<string, IsoUnit>();
    for (const u of everyone()) {
      const art = spriteOf(u);
      display.set(u.id, {
        id: u.id, x: u.pos[0], y: u.pos[1], facing: u.facing, side: u.side, frames: art.frames, anchor: art.anchor,
        hp: u.hp, maxHp: u.maxHp, alive: alive(u), hitAt: -1e9, lunge: null, lungeAt: -1e9, flip: flipFor(u.facing, false),
      });
    }
    const sync = () => {
      for (const u of everyone()) {
        const d = display.get(u.id)!;
        Object.assign(d, { x: u.pos[0], y: u.pos[1], facing: u.facing, hp: Math.max(0, u.hp), maxHp: u.maxHp, alive: alive(u), flip: flipFor(u.facing, d.flip) });
      }
    };

    // --- выбор и режимы ---
    let selected: Unit | null = battle.aliveParty().find((u) => battle.canAct(u)) ?? null;
    let inspected: Unit | null = null;
    let mode: Mode = { kind: "idle" };
    let busy = false;
    let finished = false;
    let enemyPhase = false;
    let resolveFn: (r: Result) => void = () => {};

    const aiming = () => mode.kind === "skill" || mode.kind === "item";

    const highlights = (): Map<string, Highlight> => {
      const out = new Map<string, Highlight>();
      if (busy || finished || !selected || !alive(selected)) return out;
      const u = selected;
      if (aiming()) {
        for (let y = 0; y < battle.arena.height; y++)
          for (let x = 0; x < battle.arena.width; x++) if (manhattan(u.pos, [x, y]) <= SKILL_RANGE) out.set(key([x, y]), "range");
        for (const e of battle.aliveEnemies()) if (manhattan(u.pos, e.pos) <= SKILL_RANGE) out.set(key(e.pos), "attack");
      } else if (battle.canAct(u)) {
        if (!u.moved) for (const r of battle.moves(u).values()) if (!battle.unitAt(r.cell)) out.set(key(r.cell), "move");
        for (const e of battle.aliveEnemies()) if (manhattan(u.pos, e.pos) <= u.range) out.set(key(e.pos), "attack");
      }
      out.set(key(u.pos), "selected");
      if (inspected && alive(inspected)) out.set(key(inspected.pos), "target");
      return out;
    };

    // --- отрисовка и масштаб ---
    let raf = 0;
    const frame = (now: number) => {
      view.draw([...display.values()], highlights(), now);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    const fit = () => {
      const r = stage.getBoundingClientRect();
      const k = Math.max(1, Math.min(4, Math.floor(Math.min(r.width / view.canvas.width, r.height / view.canvas.height) * 2) / 2));
      view.canvas.style.width = `${view.canvas.width * k}px`;
      view.canvas.style.height = `${view.canvas.height * k}px`;
    };
    const onResize = () => {
      fit();
      labels();
    };
    window.addEventListener("resize", onResize);

    /** Логическая точка холста → координаты внутри stage. */
    const toStage = (lx: number, ly: number): [number, number] => {
      const cr = view.canvas.getBoundingClientRect();
      const sr = stage.getBoundingClientRect();
      const k = cr.width / view.canvas.width;
      return [cr.left - sr.left + lx * k, cr.top - sr.top + ly * k];
    };
    const overHead = (u: { x: number; y: number }): [number, number] => {
      const [cx, cy] = view.cellCenter(u.x, u.y);
      return toStage(cx, cy - 34);
    };

    const floatText = (u: IsoUnit, text: string, cls: string) => {
      const [x, y] = overHead(u);
      const n = el("div", { className: `floater ${cls}`, textContent: text });
      n.style.left = `${x}px`;
      n.style.top = `${y}px`;
      floaters.append(n);
      setTimeout(() => n.remove(), 1200);
    };

    /** Подписи «≈7 · в спину» над врагами, которых выбранный боец может достать. */
    const labels = () => {
      floaters.querySelectorAll(".preview").forEach((n) => n.remove());
      if (busy || finished || !selected || !battle.canAct(selected)) return;
      const u = selected;
      const reach = aiming() ? SKILL_RANGE : u.range;
      for (const e of battle.aliveEnemies()) {
        if (manhattan(u.pos, e.pos) > reach) continue;
        const p = battle.preview(u, e);
        const dmg = mode.kind === "skill" ? battle.strike(u, e, damageOf(mode.skill.effect as Effect[])).dmg
          : mode.kind === "item" ? damageOf(mode.item.effect as Effect[]) : p.dmg;
        const bonus = mode.kind !== "item" && (p.side !== "front" || p.high);
        const tag = mode.kind === "item" ? "" : [SIDE_TEXT[p.side], p.high ? "сверху" : ""].filter(Boolean).join(", ");
        const [x, y] = overHead(display.get(e.id)!);
        const n = el("div", { className: `preview${bonus ? " bonus" : ""}`, textContent: `≈${dmg}${tag ? ` · ${tag}` : ""}` });
        n.style.left = `${x}px`;
        n.style.top = `${y - 16}px`;
        floaters.append(n);
      }
    };

    // --- шапка, карточка бойца, кнопки ---
    const renderHead = () => {
      const pips = el("div", { className: "pips" }, ...Array.from({ length: MAX_POINTS }, (_, i) => el("i", { className: i < battle.points ? "on" : "" })));
      const chips = el("div", { className: "party-chips" }, ...battle.party.map((u) => {
        const b = el("button", {
          className: `chip${u === selected ? " on" : ""}${alive(u) && battle.canAct(u) ? "" : " done"}`,
          disabled: !alive(u) || busy || finished,
          title: `${u.name}: ${Math.max(0, u.hp)}/${u.maxHp}`,
        }, el("span", { textContent: u.name.split(" ")[0] }), el("i", { style: `width:${Math.max(0, (100 * u.hp) / u.maxHp)}%` }));
        b.addEventListener("click", () => {
          selected = u;
          inspected = null;
          setMode({ kind: "idle" });
        });
        return b;
      }));
      head.replaceChildren(
        el("div", { className: "round", textContent: `Раунд ${battle.round}${enemyPhase ? " · ход врагов" : ""}` }),
        chips,
        el("div", { className: "points", title: "Кураж копится за попадания, удары во фланг и в спину, удары с высоты и победы" },
          el("span", { textContent: `Кураж ${battle.points}` }), pips),
        el("div", { className: "gold", textContent: `◆ ${battle.wallet(null)}` }),
      );
    };

    const unitCard = (u: Unit) => {
      const ch = world.characters.get(u.look);
      const e = world.enemies.get(u.look);
      const emotion = u.side === "party" ? (u.hp < u.maxHp * 0.3 ? "scared" : "neutral") : "angry";
      const face = ch ? pixel(portraitCanvas(ch.appearance, emotion, ch.id), 1)
        : e && "body" in e.appearance ? pixel(creatureCanvas(e.appearance, e.id), 1)
        : e && !("body" in e.appearance) ? pixel(portraitCanvas(e.appearance, "angry", e.id), 1) : el("div");
      face.classList.add("card-face");
      const buffs = u.buffs.map((b) => `${b.stat === "attack" ? "атака" : "защита"} ${b.delta > 0 ? "+" : ""}${b.delta}`);
      const status = u.side === "enemy" ? "Враг: стрелка у ног — куда он смотрит. Бейте сбоку и сзади."
        : !alive(u) ? "Выбыл из боя"
        : u.acted ? "Ход сделан"
        : u.moved ? "Переместился — осталось действие"
        : "Может пойти и действовать";
      return el("div", { className: `card ${u.side}` }, face, el("div", { className: "card-body" },
        el("b", { textContent: u.name }),
        bar(Math.max(0, u.hp), u.maxHp, "hp"),
        u.maxFocus ? bar(u.focus, u.maxFocus, "focus") : el("span"),
        el("small", { textContent: `Атака ${stat(u, "attack")} · защита ${stat(u, "defense")} · ход ${u.move + u.moveBonus} · дальность ${u.range}` }),
        ...(buffs.length ? [el("small", { className: "buffs", textContent: buffs.join(", ") })] : []),
        el("small", { className: "status", textContent: status })));
    };

    const renderCard = () => {
      const u = inspected ?? selected;
      card.replaceChildren(u ? unitCard(u) : el("div"));
    };

    const itemsInBag = (): [Item, number][] =>
      Object.entries(state.inventory).flatMap(([id, n]) => {
        const it = world.items.get(id);
        return it?.kind === "consumable" && n > 0 ? [[it, n] as [Item, number]] : [];
      });

    const back = () => button("Назад", () => setMode({ kind: "idle" }), "btn btn-ghost");

    const tacticButton = (t: Tactic, u: Unit, open: boolean) => {
      const gold = (t.currency ?? "points") === "gold";
      const price = gold ? `${t.cost} ◆` : `${t.cost} кураж`;
      const hint = !open && t.unlock ? `Откроется: ${describe(t.unlock as Condition, world)}`
        : gold && battle.goldUsed.has(t.id) ? "Уже куплено в этом бою" : t.description;
      const b = el("button", { className: `tactic${open ? "" : " locked"}${gold ? " gold" : ""}`, disabled: !open || busy || !battle.tacticOk(u, t) },
        pixel(iconCanvas(t.icon, t.tier ?? 1), 2),
        el("span", { className: "tactic-text" }, el("b", { textContent: `${t.name} · ${price}` }), el("small", { textContent: hint })));
      b.addEventListener("click", () => void act(() => battle.useTactic(u, t), false));
      return b;
    };

    const renderActions = () => {
      if (finished) return;
      const u = selected;
      const can = !busy && !!u && battle.canAct(u);
      if (mode.kind === "menu" && u) {
        if (mode.menu === "skills") {
          const list = u.skills.map((id) => world.skills.get(id)).filter((s): s is Skill => !!s);
          actions.replaceChildren(...list.map((s) => button(`${s.name} · ${s.cost_focus} фок.`, () => pickSkill(s), "btn", !can || u.focus < s.cost_focus)), back());
        } else if (mode.menu === "items") {
          actions.replaceChildren(...itemsInBag().map(([it, n]) => button(`${it.name} ×${n}`, () => pickItem(it), "btn", !can)), back());
        } else {
          const open = new Set(battle.tactics.map((t) => t.id));
          const list = el("div", { className: "tactics" }, ...(world.game.tactics ?? []).map((t) => tacticButton(t, u, open.has(t.id))));
          actions.replaceChildren(list, back());
        }
        return;
      }
      if (aiming()) {
        const name = mode.kind === "skill" ? mode.skill.name : mode.kind === "item" ? mode.item.name : "";
        actions.replaceChildren(el("span", { className: "hint", textContent: `${name}: коснитесь врага (до ${SKILL_RANGE} клеток)` }), back());
        return;
      }
      const left = battle.aliveParty().filter((p) => battle.canAct(p)).length;
      actions.replaceChildren(
        button("Навык", () => setMode({ kind: "menu", menu: "skills" }), "btn", !can || !u!.skills.some((id) => world.skills.has(id))),
        button("Предмет", () => setMode({ kind: "menu", menu: "items" }), "btn", !can || !itemsInBag().length),
        button("Тактика", () => setMode({ kind: "menu", menu: "tactics" }), "btn btn-tactic", busy || !u || !alive(u) || u.tacticUsed || u.acted),
        button("Защита", () => void act(() => battle.defend(u!)), "btn", !can),
        ...(u?.kind === "hero" ? [button("Побег", () => void act(() => battle.flee(u)), "btn", !can)] : []),
        button("Конец хода", () => void endTurn(), `btn btn-primary${left ? "" : " pulse"}`, busy),
      );
    };

    const renderLog = () => {
      log.replaceChildren(...battle.log.filter((e) => e.text).slice(-3).map((e) =>
        el("p", { className: e.actor.startsWith("e") ? "them" : "you", textContent: e.text })));
    };

    const refresh = () => {
      renderHead();
      renderCard();
      renderActions();
      renderLog();
      labels();
    };

    const setMode = (m: Mode) => {
      mode = m;
      refresh();
    };

    const pickSkill = (s: Skill) => {
      const u = selected;
      if (!u) return;
      if (s.target === "self") void act(() => battle.skill(u, s, null));
      else setMode({ kind: "skill", skill: s });
    };
    const pickItem = (it: Item) => {
      const u = selected;
      if (!u) return;
      if (damageOf(it.effect as Effect[]) > 0) setMode({ kind: "item", item: it });
      else void act(() => battle.item(u, it, null, take));
    };

    // --- анимация событий движка ---
    const glide = (u: IsoUnit, to: Cell) => new Promise<void>((resolve) => {
      const from: [number, number] = [u.x, u.y];
      const t0 = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - t0) / STEP_MS);
        u.x = from[0] + (to[0] - from[0]) * k;
        u.y = from[1] + (to[1] - from[1]) * k;
        if (k < 1) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });

    const walk = async (d: IsoUnit, path: Cell[]) => {
      for (const c of path.slice(1)) {
        d.facing = [c[0] - Math.round(d.x), c[1] - Math.round(d.y)];
        d.flip = flipFor(d.facing, d.flip);
        await glide(d, c);
      }
    };

    const replay = async (events: BattleEvent[]) => {
      for (const ev of events) {
        const actor = display.get(ev.actor);
        const target = ev.target ? display.get(ev.target) : undefined;
        if (ev.kind === "move" && actor && ev.path) {
          await walk(actor, ev.path);
          continue;
        }
        if (ev.kind === "hit" && target) {
          if (actor && actor !== target) {
            const u = everyone().find((x) => x.id === ev.actor);
            if (u) {
              actor.facing = u.facing;
              actor.flip = flipFor(u.facing, actor.flip);
            }
            actor.lunge = [target.x, target.y];
            actor.lungeAt = performance.now();
            await sleep(120);
          }
          target.hitAt = performance.now();
          target.hp = Math.max(0, target.hp - ev.amount);
          const tag = ev.side === "back" ? " в спину!" : ev.side === "flank" ? " фланг" : "";
          const cls = target.side === "party" ? "hurt" : ev.side !== "front" || ev.high ? "crit" : "dmg";
          floatText(target, `−${ev.amount}${tag}`, cls);
          await sleep(360);
          if (target.hp <= 0) target.alive = false;
        } else if (ev.kind === "heal" && target) {
          target.hp = Math.min(target.maxHp, target.hp - ev.amount);
          floatText(target, `+${-ev.amount}`, "heal");
          await sleep(300);
        } else if (ev.kind === "buff" && target) {
          floatText(target, ev.text.split(": ").pop() ?? "", "buff");
          await sleep(280);
        } else if (ev.kind === "info" && ev.text) {
          await sleep(140);
        }
        if (ev.text) {
          log.append(el("p", { className: ev.actor.startsWith("e") ? "them" : "you", textContent: ev.text }));
          while (log.children.length > 3) log.firstChild!.remove();
        }
      }
      sync();
    };

    /** Действие отряда: применить в движке и показать его события. */
    const act = async (fn: () => boolean, autoNext = true) => {
      if (busy || finished) return;
      const from = battle.log.length;
      if (!fn()) return;
      busy = true;
      mode = { kind: "idle" };
      refresh();
      await replay(battle.log.slice(from));
      busy = false;
      if (battle.result) return finish();
      if (autoNext && selected && !battle.canAct(selected)) selected = battle.aliveParty().find((p) => battle.canAct(p)) ?? selected;
      refresh();
    };

    const moveTo = async (u: Unit, c: Cell) => {
      const path = battle.path(battle.moves(u), c);
      if (!battle.move(u, c)) return;
      busy = true;
      refresh();
      await walk(display.get(u.id)!, path);
      sync();
      busy = false;
      refresh();
    };

    const endTurn = async () => {
      if (busy || finished) return;
      busy = true;
      mode = { kind: "idle" };
      inspected = null;
      refresh();
      enemyPhase = true;
      renderHead();
      banner("Ход врагов", "enemy");
      await sleep(500);
      const from = battle.log.length;
      battle.endTurn();
      await replay(battle.log.slice(from));
      enemyPhase = false;
      busy = false;
      if (battle.result) return finish();
      selected = battle.aliveParty().find((p) => battle.canAct(p)) ?? null;
      banner(`Раунд ${battle.round} · ваш ход`, "party");
      refresh();
    };

    const close = (r: Result) => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      this.root.classList.add("hidden");
      delete (window as unknown as { __battle?: unknown }).__battle;
      resolveFn(r);
    };

    const finish = () => {
      finished = true;
      sync();
      labels();
      renderHead();
      const r = battle.result!;
      const text = r === "win" ? "Победа!" : r === "lose" ? "Поражение…" : "Вы сбежали.";
      actions.replaceChildren(el("div", { className: `battle-result ${r}`, textContent: text }), button("Продолжить", () => close(r), "btn btn-primary"));
    };

    // --- тапы по полю ---
    const onCell = (c: Cell) => {
      const target = battle.unitAt(c);
      const u = selected;
      if (aiming() && u) {
        if (target?.side === "enemy" && manhattan(u.pos, target.pos) <= SKILL_RANGE) {
          if (mode.kind === "skill") {
            const s = mode.skill;
            void act(() => battle.skill(u, s, target));
          } else if (mode.kind === "item") {
            const it = mode.item;
            void act(() => battle.item(u, it, target, take));
          }
        } else setMode({ kind: "idle" });
        return;
      }
      if (target?.side === "party") {
        selected = target;
        inspected = null;
        return setMode({ kind: "idle" });
      }
      if (target?.side === "enemy") {
        if (u && battle.canAct(u) && manhattan(u.pos, target.pos) <= u.range) {
          inspected = null;
          void act(() => battle.attack(u, target));
        } else {
          inspected = target;
          refresh();
        }
        return;
      }
      inspected = null;
      if (u && battle.canAct(u) && !u.moved && battle.moves(u).has(key(c))) void moveTo(u, c);
      else refresh();
    };
    /** Боец под точкой холста: тап по фигуре важнее клетки, которую она закрывает. Ближние — первыми. */
    const unitAtPoint = (lx: number, ly: number): Cell | null => {
      const hits = [...display.values()].filter((d) => {
        if (!d.alive) return false;
        const [cx, cy] = view.cellCenter(d.x, d.y);
        return Math.abs(lx - cx) <= 8 && ly <= cy + 3 && ly >= cy - 30;
      });
      hits.sort((a, b) => b.x + b.y - (a.x + a.y));
      return hits.length ? [Math.round(hits[0].x), Math.round(hits[0].y)] : null;
    };
    /** Какая клетка под точкой холста: клетка с бойцом важнее фигуры, которая её закрывает; иначе фигура, иначе клетка. */
    const resolve = (lx: number, ly: number): Cell | null => {
      const ground = view.pick(lx, ly);
      return ground && battle.unitAt(ground) ? ground : unitAtPoint(lx, ly) ?? ground;
    };
    view.canvas.addEventListener("click", (ev) => {
      if (busy || finished) return;
      const r = view.canvas.getBoundingClientRect();
      const k = r.width / view.canvas.width;
      const c = resolve((ev.clientX - r.left) / k, (ev.clientY - r.top) / k);
      if (c) onCell(c);
    });

    // хук для сквозного теста: где на экране клетка и идёт ли анимация
    (window as unknown as { __battle: unknown }).__battle = {
      battle,
      busy: () => busy,
      finished: () => finished,
      selected: () => selected?.id ?? null,
      cellScreen: (c: Cell, lift = 0) => {
        const [cx, cy] = view.cellCenter(c[0], c[1]);
        const cr = view.canvas.getBoundingClientRect();
        const k = cr.width / view.canvas.width;
        return { x: cr.left + cx * k, y: cr.top + (cy - lift) * k };
      },
      /** Видимая точка клетки или фигуры на ней, которую тап точно отнесёт к этой клетке (центр может закрывать холм спереди). */
      pointFor: (c: Cell) => {
        const [cx, cy] = view.cellCenter(c[0], c[1]);
        const cr = view.canvas.getBoundingClientRect();
        const k = cr.width / view.canvas.width;
        for (const [dx, dy] of [[0, 0], [0, -6], [0, -12], [0, -18], [0, -24], [-5, 2], [5, 2], [-8, 0], [8, 0], [0, 4]]) {
          const hit = resolve(cx + dx, cy + dy);
          if (hit && hit[0] === c[0] && hit[1] === c[1]) return { x: cr.left + (cx + dx) * k, y: cr.top + (cy + dy) * k };
        }
        return null;
      },
    };

    requestAnimationFrame(onResize);
    refresh();
    setTimeout(() => banner("Бой! Ваш ход", "party"), 50);
    return new Promise<Result>((resolve) => (resolveFn = resolve));
  }
}
