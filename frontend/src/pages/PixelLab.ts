// /lab — ручная проверка библиотеки деталей и внешности из игры (SPEC §5.7.6). В навигации не показывается.

import demo from "../data/demo_game.json";
import { BackgroundView, backgroundSeed } from "../pixel/background";
import { ids, library } from "../pixel/library";
import { randomBackground, randomCreature, randomPortrait } from "../pixel/random";
import { CREATURE_SCALE, creatureCanvas, fitScale, portraitCanvas, scaled, type Emotion } from "../pixel/sprite";
import { iconCanvas, tileCanvas } from "../pixel/tiles";
import { ANIMS, FPS, walkerFrames, type Anim } from "../pixel/walker";
import type { BackgroundSpec, CreatureSpec, Game, PortraitSpec } from "../types/game";
import { renderLevel } from "../world/level";

const EMOTIONS = library.layout.portrait.emotions as Emotion[];
const EMOTION_LABELS: Record<Emotion, string> = {
  neutral: "спокойствие", angry: "злость", sad: "грусть", happy: "радость", scared: "страх", surprised: "удивление",
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, unknown> = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props) as HTMLElementTagNameMap[K];
  node.append(...children);
  return node;
}

function select(label: string, options: string[], value: string | undefined, onChange: (v: string) => void): HTMLLabelElement {
  const s = el("select");
  for (const o of options) s.append(el("option", { value: o, textContent: o, selected: o === (value ?? "") }));
  s.addEventListener("change", () => onChange(s.value));
  return el("label", { className: "field" }, el("span", { textContent: label }), s);
}

const palette = (group: "skin_tones" | "hair_colors" | "eye_colors" | "cloth_colors") => Object.keys(library.palettes[group]);
let seedCounter = Date.now() % 100000;
const nextSeed = () => ++seedCounter;

let stopBackgrounds: (() => void)[] = [];
function stopAll(): void {
  stopBackgrounds.forEach((s) => s());
  stopBackgrounds = [];
}

function backgroundNode(spec: BackgroundSpec, seed: number, width: number, animate = true): HTMLCanvasElement {
  const view = new BackgroundView(spec, seed, animate);
  stopBackgrounds.push(() => view.stop());
  const scale = fitScale(160, width, 1, 8);
  view.canvas.style.width = `${160 * scale}px`;
  view.canvas.style.height = `${90 * scale}px`;
  return view.canvas;
}

/** Холст, перебирающий кадры с заданной частотой. */
function animated(frames: HTMLCanvasElement[], fps: number, scale: number, flip = false): HTMLCanvasElement {
  const out = scaled(frames[0], scale);
  if (flip) out.style.transform = "scaleX(-1)";
  const ctx = out.getContext("2d")!;
  let i = 0;
  const timer = setInterval(() => {
    i = (i + 1) % frames.length;
    ctx.clearRect(0, 0, out.width, out.height);
    ctx.drawImage(frames[i], 0, 0);
  }, 1000 / fps);
  stopBackgrounds.push(() => clearInterval(timer));
  return out;
}

const ANIM_LABELS: Record<Anim, string> = { idle: "стоит", walk: "идёт", climb: "лезет" };

function walkerStrip(spec: PortraitSpec, key?: string): HTMLElement {
  const frames = walkerFrames(spec, key);
  return el("div", { className: "emotions" }, ...ANIMS.flatMap((a) => [
    el("figure", { className: "dark" }, animated(frames[a], FPS[a], 4), el("figcaption", { textContent: ANIM_LABELS[a] })),
  ]), el("figure", { className: "dark" }, animated(frames.walk, FPS.walk, 4, true), el("figcaption", { textContent: "идёт влево" })));
}

function jsonBox(value: unknown, onApply: (v: any) => void): HTMLElement {
  const area = el("textarea", { className: "json", value: JSON.stringify(value, null, 2), spellcheck: false });
  const apply = el("button", { textContent: "Применить JSON" });
  apply.addEventListener("click", () => {
    try {
      onApply(JSON.parse(area.value));
    } catch (e) {
      alert(`Не JSON: ${(e as Error).message}`);
    }
  });
  return el("div", { className: "json-box" }, area, apply);
}

// --- портрет ---

function portraitTab(root: HTMLElement, initial: PortraitSpec): void {
  let spec = { ...initial };
  const render = () => {
    root.replaceChildren();
    const set = (key: keyof PortraitSpec) => (v: string) => {
      spec = { ...spec, [key]: v === "—" ? undefined : v };
      render();
    };
    const acc = spec.accessory ?? [];
    const setAcc = (i: number) => (v: string) => {
      const next = [...acc];
      next[i] = v;
      spec = { ...spec, accessory: next.filter((a) => a && a !== "—") };
      render();
    };
    const form = el("div", { className: "form" },
      select("голова", ids("head"), spec.head, set("head")),
      select("кожа", palette("skin_tones"), spec.skin, set("skin")),
      select("причёска", ["none", ...ids("hair")], spec.hair, set("hair")),
      select("цвет волос", palette("hair_colors"), spec.hair_color, set("hair_color")),
      select("глаза", ids("eyes"), spec.eyes, set("eyes")),
      select("цвет глаз", palette("eye_colors"), spec.eye_color, set("eye_color")),
      select("брови", ids("brows"), spec.brows, set("brows")),
      select("рот", ids("mouth"), spec.mouth, set("mouth")),
      select("борода", ["—", ...ids("facial_hair")], spec.facial_hair ?? "—", set("facial_hair")),
      select("наряд", ids("outfit"), spec.outfit, set("outfit")),
      select("цвет наряда", palette("cloth_colors"), spec.outfit_color, set("outfit_color")),
      select("акцент", palette("cloth_colors"), spec.accent_color, set("accent_color")),
      select("аксессуар 1", ["—", ...ids("accessory")], acc[0] ?? "—", setAcc(0)),
      select("аксессуар 2", ["—", ...ids("accessory")], acc[1] ?? "—", setAcc(1)),
      select("фон", palette("cloth_colors"), spec.bg_color, set("bg_color")),
    );
    const random = el("button", { className: "primary", textContent: "Случайно" });
    random.addEventListener("click", () => {
      spec = randomPortrait(nextSeed());
      render();
    });
    const big = scaled(portraitCanvas(spec), fitScale(48, Math.min(root.clientWidth || 360, 400), 3, 8));
    const strip = el("div", { className: "emotions" },
      ...EMOTIONS.map((e) => el("figure", {}, scaled(portraitCanvas(spec, e), 3), el("figcaption", { textContent: EMOTION_LABELS[e] }))));
    stopAll();
    root.append(
      el("div", { className: "lab-row" }, el("div", { className: "preview" }, big, random), form),
      strip,
      el("h3", { textContent: "На карте" }),
      walkerStrip(spec),
      jsonBox(spec, (v) => { spec = v; render(); }),
    );
  };
  render();
}

// --- существо ---

function creatureTab(root: HTMLElement, initial: CreatureSpec): void {
  let spec = { ...initial };
  const render = () => {
    root.replaceChildren();
    const feats = spec.features ?? [];
    const setFeat = (i: number) => (v: string) => {
      const next = [...feats];
      next[i] = v;
      spec = { ...spec, features: next.filter((f) => f && f !== "—") };
      render();
    };
    const form = el("div", { className: "form" },
      select("тело", ids("creature_body"), spec.body, (v) => { spec = { ...spec, body: v }; render(); }),
      select("цвет", palette("cloth_colors"), spec.color, (v) => { spec = { ...spec, color: v }; render(); }),
      select("акцент", palette("cloth_colors"), spec.accent_color, (v) => { spec = { ...spec, accent_color: v }; render(); }),
      ...[0, 1, 2].map((i) => select(`особенность ${i + 1}`, ["—", ...ids("creature_feature")], feats[i] ?? "—", setFeat(i))),
      select("размер", ["small", "medium", "large"], spec.size, (v) => { spec = { ...spec, size: v as CreatureSpec["size"] }; render(); }),
    );
    const random = el("button", { className: "primary", textContent: "Случайно" });
    random.addEventListener("click", () => { spec = randomCreature(nextSeed()); render(); });
    const scale = Math.round(3 * CREATURE_SCALE[spec.size]);
    root.append(
      el("div", { className: "lab-row" }, el("div", { className: "preview dark" }, scaled(creatureCanvas(spec), scale), random), form),
      jsonBox(spec, (v) => { spec = v; render(); }),
    );
  };
  render();
}

// --- фон ---

function backgroundTab(root: HTMLElement, initial: BackgroundSpec): void {
  let spec: BackgroundSpec = { ...initial, props: [...(initial.props ?? [])] };
  const render = () => {
    stopAll();
    root.replaceChildren();
    const up = (patch: Partial<BackgroundSpec>) => { spec = { ...spec, ...patch }; render(); };
    const props = spec.props ?? [];
    const propFields = [0, 1, 2, 3, 4].flatMap((i) => {
      const p = props[i];
      const xInput = el("input", { type: "number", min: "0", max: "160", value: String(p?.x ?? 20 + i * 30) });
      xInput.addEventListener("change", () => {
        const next = [...props];
        if (next[i]) next[i] = { ...next[i], x: Number(xInput.value) };
        up({ props: next });
      });
      return [
        select(`предмет ${i + 1}`, ["—", ...ids("prop")], p?.id ?? "—", (v) => {
          const next = [...props];
          if (v === "—") next.splice(i, 1);
          else next[i] = { id: v, x: p?.x ?? 20 + i * 30 };
          up({ props: next });
        }),
        el("label", { className: "field" }, el("span", { textContent: "x" }), xInput),
      ];
    });
    const form = el("div", { className: "form" },
      select("место", ["outdoor", "indoor"], spec.setting, (v) => up({ setting: v as BackgroundSpec["setting"] })),
      select("время", ["day", "dusk", "night"], spec.time, (v) => up({ time: v as BackgroundSpec["time"] })),
      select("небо", ["—", ...ids("sky")], spec.sky ?? "—", (v) => up({ sky: v === "—" ? undefined : v })),
      select("дальний план", ids("far"), spec.far, (v) => up({ far: v })),
      select("земля", ids("ground"), spec.ground, (v) => up({ ground: v })),
      select("overlay", ["none", "rain", "fog", "snow", "dust"], spec.overlay ?? "none", (v) => up({ overlay: v as BackgroundSpec["overlay"] })),
      select("настроение", Object.keys(library.palettes.mood_palettes), spec.mood_palette, (v) => up({ mood_palette: v })),
      ...propFields,
    );
    const random = el("button", { className: "primary", textContent: "Случайно" });
    random.addEventListener("click", () => { spec = randomBackground(nextSeed()); render(); });
    root.append(
      el("div", { className: "preview wide" }, backgroundNode(spec, 1, Math.min(root.clientWidth || 360, 960)), random),
      form,
      jsonBox(spec, (v) => { spec = v; render(); }),
    );
  };
  render();
}

// --- демо-игра ---

function gameTab(root: HTMLElement, game: Game, gameId: string): void {
  stopAll();
  root.replaceChildren();
  const people = [game.hero, ...(game.characters ?? [])];
  root.append(el("h2", { textContent: `Персонажи — ${game.meta.title}` }));
  for (const c of people) {
    root.append(el("div", { className: "character" },
      el("div", { className: "emotions" }, ...EMOTIONS.map((e) => scaled(portraitCanvas(c.appearance, e, c.id), 2))),
      el("div", {}, el("b", { textContent: `${c.name} (${c.role})` }), el("p", { textContent: c.description }))));
  }
  root.append(el("h2", { textContent: "Враги" }));
  root.append(el("div", { className: "enemies" }, ...(game.enemies ?? []).map((e) => {
    const art = "body" in e.appearance
      ? scaled(creatureCanvas(e.appearance), Math.round(2 * CREATURE_SCALE[e.appearance.size]))
      : scaled(portraitCanvas(e.appearance, "angry", e.id), 2);
    return el("figure", { className: "dark" }, art, el("figcaption", { textContent: `${e.name} · tier ${e.tier}` }));
  })));
  root.append(el("h2", { textContent: "Локации" }));
  for (const loc of game.locations) {
    root.append(el("figure", { className: "scene" },
      backgroundNode(loc.background, backgroundSeed(gameId, loc.id), Math.min(root.clientWidth || 360, 640)),
      el("figcaption", { textContent: `${loc.id} — ${loc.title} · ${loc.theme}, этажей: ${loc.floors}, объектов: ${loc.objects?.length ?? 0}` })));
  }
}

// --- тайлсеты ---

function tilesetTab(root: HTMLElement): void {
  let theme = ids("tileset")[0];
  let mood = "warm_candle";
  let time: BackgroundSpec["time"] = "day";
  const render = () => {
    root.replaceChildren();
    const ts = library.slots.tileset.get(theme)!;
    const form = el("div", { className: "form" },
      select("тайлсет", ids("tileset"), theme, (v) => { theme = v; render(); }),
      select("настроение", Object.keys(library.palettes.mood_palettes), mood, (v) => { mood = v; render(); }),
      select("время", ["day", "dusk", "night"], time, (v) => { time = v as typeof time; render(); }),
    );
    const cell = (name: string, decor = false) => {
      const c = tileCanvas(theme, name, mood, time, decor);
      return c ? el("figure", { className: "dark" }, scaled(c, 3), el("figcaption", { textContent: name })) : el("span");
    };
    root.append(form, el("p", { textContent: `${ts.description} · ${ts.setting}` }),
      el("div", { className: "emotions" }, ...Object.keys(ts.tiles ?? {}).map((n) => cell(n))),
      el("h3", { textContent: "Декорации" }),
      el("div", { className: "emotions" }, ...Object.keys(ts.decor ?? {}).map((n) => cell(n, true))));
  };
  render();
}

// --- уровни демо-игры ---

function levelTab(root: HTMLElement, game: Game, gameId: string): void {
  stopAll();
  root.replaceChildren();
  for (const loc of game.locations) {
    const frames = [0, 1].map((f) => renderLevel(game, gameId, loc.id, f));
    const width = Math.min(root.clientWidth || 360, 1060);
    const scale = Math.max(1, Math.floor(width / frames[0].width));
    root.append(el("figure", { className: "scene" }, animated(frames, 2, scale),
      el("figcaption", { textContent: `${loc.id} — ${loc.title} · ${loc.theme} · ${game.levels![loc.id].width}×${game.levels![loc.id].height} тайлов` })));
  }
}

// --- иконки ---

function iconsTab(root: HTMLElement): void {
  root.replaceChildren();
  for (const tier of [1, 2, 3, 4, 5]) {
    root.append(el("h3", { textContent: `Ценность ${tier}` }), el("div", { className: "icons" },
      ...ids("icon").map((id) => el("figure", { title: library.slots.icon.get(id)!.description }, scaled(iconCanvas(id, tier), 3),
        el("figcaption", { textContent: id })))));
  }
}

// --- сетки для скриншотов: /lab?grid=portraits|backgrounds&seed=N&count=M ---

function gridPage(root: HTMLElement, kind: string, seed: number, count: number): void {
  root.className = "grid-page";
  for (let i = 0; i < count; i++) {
    const s = seed * 1000 + i;
    if (kind === "portraits") root.append(el("figure", {}, scaled(portraitCanvas(randomPortrait(s)), 4)));
    else if (kind === "walkers") {
      const spec = randomPortrait(s);
      const frames = walkerFrames(spec);
      root.append(el("figure", { className: "walker-row dark" }, scaled(portraitCanvas(spec), 2),
        ...ANIMS.flatMap((a) => frames[a].map((f) => scaled(f, 2)))));
    } else if (kind === "walking") {
      const frames = walkerFrames(randomPortrait(s));
      root.append(el("figure", { className: "dark" }, animated(frames.walk, FPS.walk, 4)));
    }
    else if (kind === "creatures") root.append(el("figure", { className: "dark" }, scaled(creatureCanvas(randomCreature(s)), 3)));
    else if (kind === "levels") {
      const game = demo as unknown as Game;
      if (i < game.locations.length) root.append(el("figure", {}, scaled(renderLevel(game, "demo", game.locations[i].id), 2)));
    } else root.append(el("figure", {}, backgroundNode(randomBackground(s), s, 480, false)));
  }
  root.dataset.ready = "1";
}

export function mountPixelLab(root: HTMLElement): void {
  const params = new URLSearchParams(location.search);
  const grid = params.get("grid");
  if (grid) {
    gridPage(root, grid, Number(params.get("seed") ?? 1), Number(params.get("count") ?? (grid === "portraits" ? 20 : 10)));
    return;
  }
  const game = demo as unknown as Game;
  const tabs: [string, (body: HTMLElement) => void][] = [
    ["Портрет", (b) => portraitTab(b, game.hero.appearance)],
    ["Существо", (b) => creatureTab(b, randomCreature(nextSeed()))],
    ["Фон", (b) => backgroundTab(b, game.locations[0].background)],
    ["Демо-игра", (b) => gameTab(b, game, "demo")],
    ["Тайлсеты", (b) => tilesetTab(b)],
    ["Уровни", (b) => levelTab(b, game, "demo")],
    ["Иконки", (b) => iconsTab(b)],
  ];
  const body = el("main", { className: "lab-body" });
  const nav = el("nav", { className: "tabs" });
  const open = (i: number) => {
    stopAll();
    nav.querySelectorAll("button").forEach((b, j) => b.classList.toggle("active", i === j));
    tabs[i][1](body);
    history.replaceState(null, "", `?tab=${i}`);
  };
  tabs.forEach(([name], i) => {
    const b = el("button", { textContent: name });
    b.addEventListener("click", () => open(i));
    nav.append(b);
  });
  root.append(el("header", { className: "lab-header" }, el("h1", { textContent: "PixelLab" }), nav), body);
  open(Math.min(tabs.length - 1, Number(params.get("tab") ?? 0)));
}

