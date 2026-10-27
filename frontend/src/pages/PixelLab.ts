// /lab — ручная проверка библиотеки деталей и внешности из игры (SPEC §5.7.6). В навигации не показывается.

import demo from "../../../backend/tests/fixtures/demo_game.json";
import { BackgroundView, backgroundSeed } from "../pixel/background";
import { ids, library } from "../pixel/library";
import { randomBackground, randomCreature, randomPortrait } from "../pixel/random";
import { CREATURE_SCALE, creatureCanvas, fitScale, portraitCanvas, scaled, type Emotion } from "../pixel/sprite";
import type { BackgroundSpec, CreatureSpec, Game, PortraitSpec } from "../types/game";

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

const palette = (group: keyof Omit<typeof library.palettes, "fixed" | "mood_palettes">) => Object.keys(library.palettes[group]);
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
    root.append(
      el("div", { className: "lab-row" }, el("div", { className: "preview" }, big, random), form),
      strip,
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

// --- сетки для скриншотов: /lab?grid=portraits|backgrounds&seed=N&count=M ---

function gridPage(root: HTMLElement, kind: string, seed: number, count: number): void {
  root.className = "grid-page";
  for (let i = 0; i < count; i++) {
    const s = seed * 1000 + i;
    if (kind === "portraits") root.append(el("figure", {}, scaled(portraitCanvas(randomPortrait(s)), 4)));
    else if (kind === "creatures") root.append(el("figure", { className: "dark" }, scaled(creatureCanvas(randomCreature(s)), 3)));
    else root.append(el("figure", {}, backgroundNode(randomBackground(s), s, 480, false)));
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

