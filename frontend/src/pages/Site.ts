// Главная, бриф, экран генерации (SPEC §11.1–11.3) и каталог готовых игр.

import { api, ApiError, autoFeatures, draft, type Feature, FEATURES, type GameCard, mine, type Profile, type Status } from "../api";
import { publishToggle } from "../ui/publish";
import demoGame from "../data/demo_game.json";
import { backgroundSeed, renderBackground } from "../pixel/background";
import { library } from "../pixel/library";
import { creatureMapFrames, portraitCanvas } from "../pixel/sprite";
import type { Game } from "../types/game";
import { FPS, walkerFrames } from "../pixel/walker";
import { button, el, pixel } from "../ui/dom";
import "../site.css";

const EXAMPLES = [
  "Юная травница ищет лекарство от сонной хвори, охватившей её деревню, и узнаёт, что болезнь насылает старый друг семьи.",
  "Детектив 1920-х расследует исчезновение джазовой певицы в портовом городе, где у каждого свидетеля есть тайна.",
  "Инженер просыпается на дрейфующей станции, где бортовой ИИ уверяет, что экипаж эвакуировался сто лет назад.",
];

function go(path: string): void {
  history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function nav(): HTMLElement {
  const here = location.pathname.replace(/\/$/, "") || "/";
  const link = (href: string, text: string) => {
    const a = el("a", { href, textContent: text, className: here === href ? "on" : "" });
    a.addEventListener("click", (e) => {
      e.preventDefault();
      go(href);
    });
    return a;
  };
  return el("nav", { className: "site-nav" }, link("/", "Создать игру"), link("/games", "Готовые игры"));
}

function page(...children: (Node | null)[]): HTMLElement {
  return el("main", { className: "site" }, nav(), ...children);
}


async function demoBanner(): Promise<HTMLElement | null> {
  try {
    const { provider } = await api.info();
    if (provider !== "demo") return null;
  } catch {
    return el("p", { className: "banner warn", textContent: "Сервер генерации недоступен. Демо-игра работает и без него." });
  }
  return el("p", { className: "banner", textContent: "Демо-режим: GigaChat ещё не подключён, поэтому любая идея превратится в готовую игру — «Погасший маяк», а без боёв — «Последняя смена». Весь путь — бриф, генерация, игра, ссылка — работает по-настоящему." });
}

function busyButton(b: HTMLButtonElement, text: string): () => void {
  const old = b.textContent;
  b.disabled = true;
  b.textContent = text;
  return () => {
    b.disabled = false;
    b.textContent = old;
  };
}

// --- профиль игры (§5.10): сколько боёв и насколько глубокие разговоры ---

const COMBAT_OPTIONS: [Profile["combat"], string, string][] = [
  ["tactical", "Тактические", "2–4 пошаговых боя на изометрическом поле, торговец, снаряжение."],
  ["light", "Немного", "1–3 боя, важных для сюжета. Главное — разговоры и находки."],
  ["none", "Без боёв", "Всё решают разговоры, улики и внутренние навыки героя: логика, чуткость, воля…"],
];
const DIALOGUE_OPTIONS: [Profile["dialogue"], string, string][] = [
  ["light", "Лёгкие", "Короткие живые реплики и загадка, которую надо разгадать."],
  ["rich", "Живые", "Разговоры с характером, выбор с последствиями, проверки навыков."],
  ["deep", "Глубокие", "Как в Disco Elysium: подтекст, секреты, голоса навыков, финал без правильного ответа."],
];

// дополнительные механики (§5.12): по умолчанию подбираются по боям и диалогам, автор может поменять
const FEATURE_INFO: Record<Feature, [string, string]> = {
  secrets: ["Тайники", "Спрятанные сундуки и вещи — найдёт только внимательный герой."],
  deduction: ["Улики и выводы", "Доска улик: соедини находки — получи вывод, который открывает новые разговоры."],
  crafting: ["Сбор и ремесло", "Травы, руда, обломки — и верстак, котёл или костёр, где из них что-то получается."],
  bestiary: ["Слабости врагов", "Узнай, чего боится враг, подготовь оружие — и бей наверняка."],
  puzzles: ["Головоломки", "Кодовые замки и рычаги: ответ спрятан в записках и разговорах."],
  thoughts: ["Мысли героя", "Озарения, которые герой обдумывает по дороге, — и они меняют его навыки."],
  daynight: ["Время суток", "День сменяется ночью: кто-то приходит только в темноте."],
};

function profilePicker(): HTMLElement {
  const box = el("div", { className: "profile" });
  const render = () => {
    const p = draft.profile();
    const row = <K extends keyof Profile>(key: K, title: string, options: [Profile[K], string, string][]) => {
      const current = options.find(([v]) => v === p[key])!;
      return el("div", { className: "profile-row" },
        el("span", { className: "profile-title", textContent: title }),
        el("div", { className: "segmented", role: "radiogroup" }, ...options.map(([value, label]) => {
          const b = button(label, () => {
            const next = { ...draft.profile(), [key]: value };
            draft.set("profile", JSON.stringify({ ...next, features: autoFeatures(next.combat, next.dialogue) }));
            render();
          }, `seg${value === p[key] ? " on" : ""}`);
          b.setAttribute("role", "radio");
          b.setAttribute("aria-checked", String(value === p[key]));
          return b;
        })),
        el("small", { className: "muted", textContent: current[2] }));
    };
    const features = el("div", { className: "profile-row" },
      el("span", { className: "profile-title", textContent: "Механики" }),
      el("div", { className: "features" }, ...FEATURES.map((f) => {
        const on = p.features.includes(f);
        const b = button(FEATURE_INFO[f][0], () => {
          const list = on ? p.features.filter((x) => x !== f) : FEATURES.filter((x) => x === f || p.features.includes(x));
          draft.set("profile", JSON.stringify({ ...p, features: list }));
          render();
        }, `chip-toggle${on ? " on" : ""}`);
        b.title = FEATURE_INFO[f][1];
        b.setAttribute("aria-pressed", String(on));
        if (f === "bestiary" && p.combat === "none") b.disabled = true;
        return b;
      })),
      el("small", { className: "muted", textContent: p.features.map((f) => FEATURE_INFO[f][1]).slice(0, 2).join(" ") || "Без дополнительных механик." }));
    box.replaceChildren(row("combat", "Бои", COMBAT_OPTIONS), row("dialogue", "Диалоги", DIALOGUE_OPTIONS), features);
  };
  render();
  return box;
}

async function startGame(brief: string, error: HTMLElement, b: HTMLButtonElement): Promise<void> {
  const done = busyButton(b, "Отправляем…");
  try {
    const { game_id, owner_token } = await api.create(brief, draft.profile());
    mine.add(game_id, owner_token);
    draft.set("brief", brief);
    go(`/progress/${game_id}`);
  } catch (e) {
    error.textContent = (e as ApiError).message;
    done();
  }
}

// --- главная ---

export async function mountHome(root: HTMLElement): Promise<void> {
  document.title = "Генератор RPG";
  const idea = el("textarea", { className: "idea", placeholder: "Опиши свою историю: кто герой, где всё происходит, что пошло не так…", value: draft.get("idea"), maxLength: 4000 });
  idea.addEventListener("input", () => draft.set("idea", idea.value));
  const error = el("p", { className: "error" });
  const expand = button("Развернуть в бриф", async () => {
    error.textContent = "";
    if (idea.value.trim().length < 3) return void (error.textContent = "Напишите хотя бы пару слов.");
    const done = busyButton(expand, "Пишем бриф…");
    try {
      const brief = await api.brief(idea.value.trim(), draft.profile());
      draft.set("brief", brief.brief_markdown);
      draft.set("questions", JSON.stringify(brief.questions));
      go("/brief");
    } catch (e) {
      error.textContent = (e as ApiError).message;
      done();
    }
  }, "btn");
  const create = button("Создать игру", () => {
    error.textContent = "";
    const text = idea.value.trim();
    if (text.length < 20) return void (error.textContent = "Опишите идею подробнее — хотя бы одно предложение.");
    void startGame(text, error, create);
  }, "btn btn-primary");
  const examples = el("div", { className: "examples" }, ...EXAMPLES.map((t) =>
    button(t, () => {
      idea.value = t;
      draft.set("idea", t);
    }, "example")));
  root.replaceChildren(page(
    el("h1", { textContent: "Генератор RPG" }),
    el("p", { className: "lead", textContent: "Опишите историю — ИИ превратит её в пиксельную RPG, в которую можно сыграть и поделиться ссылкой." }),
    await demoBanner(),
    idea,
    profilePicker(),
    el("div", { className: "row" }, expand, create),
    error,
    el("h3", { textContent: "Например" }),
    examples,
    el("p", { className: "muted" }, "Или ", el("a", { href: "/play/demo", textContent: "сыграйте в демо-игру «Погасший маяк»" }), "."),
  ));
}

// --- бриф ---

export function mountBrief(root: HTMLElement): void {
  document.title = "Бриф — Генератор RPG";
  const text = el("textarea", { className: "brief", value: draft.get("brief") });
  text.addEventListener("input", () => draft.set("brief", text.value));
  let questions: string[] = [];
  try {
    questions = JSON.parse(draft.get("questions") || "[]");
  } catch {
    questions = [];
  }
  const error = el("p", { className: "error" });
  const create = button("Создать игру", () => {
    error.textContent = "";
    if (text.value.trim().length < 20) return void (error.textContent = "Бриф слишком короткий.");
    void startGame(text.value.trim(), error, create);
  }, "btn btn-primary");
  root.replaceChildren(page(
    el("h1", { textContent: "Бриф" }),
    el("p", { className: "lead", textContent: "Поправьте всё, что хочется: игра будет собрана по этому тексту." }),
    questions.length ? el("div", { className: "questions" }, el("b", { textContent: "Подумайте над вопросами — ответы можно дописать прямо в бриф:" }),
      el("ul", {}, ...questions.map((q) => el("li", { textContent: q })))) : null,
    text,
    profilePicker(),
    el("div", { className: "row" }, button("← Назад", () => go("/"), "btn btn-ghost"), create),
    error,
  ));
}

// --- генерация ---

const STEPS: [string, string][] = [
  ["outline", "Каркас: герои, квесты, локации"],
  ["locations", "Локации и диалоги"],
  ["items", "Предметы, навыки, торговцы"],
  ["validate", "Проверка и починка"],
  ["levels", "Баланс и уровни"],
  ["playtest", "Тестовые прохождения"],
];
const ORDER = ["queued", "outline", "locations", "items", "validate", "fix", "balance", "levels", "playtest", "ready"];

export function mountProgress(root: HTMLElement, gameId: string): void {
  document.title = "Создаём игру…";
  const list = el("ol", { className: "steps" });
  const heroes = el("div", { className: "heroes" });
  const head = el("div", {});
  const actions = el("div", { className: "row" });
  const note = el("p", { className: "muted", textContent: "Обычно это занимает 2–4 минуты. Страницу можно не закрывать — или вернуться по этой же ссылке." });
  root.replaceChildren(page(el("h1", { textContent: "Создаём игру" }), head, list, heroes, actions, note));

  let shownHeroes = false;
  const timers: number[] = [];
  const render = (st: Status) => {
    const at = ORDER.indexOf(st.status === "fix" ? "validate" : st.status === "balance" ? "levels" : st.status);
    list.replaceChildren(...STEPS.map(([key, label]) => {
      const idx = ORDER.indexOf(key);
      const state = st.status === "ready" || at > idx ? "done" : at === idx ? "active" : "todo";
      let text = label;
      if (key === "locations" && st.detail && !Array.isArray(st.detail) && st.detail.total) text += ` (${st.detail.done}/${st.detail.total})`;
      if (key === "validate" && st.status === "fix") text += " — исправляем найденные ошибки";
      return el("li", { className: state, textContent: text });
    }));
    if (st.status === "queued") head.replaceChildren(el("p", { className: "lead", textContent: st.queue_position ? `В очереди: перед вами ${st.queue_position}.` : "Начинаем…" }));
    if (st.outline && !shownHeroes) {
      shownHeroes = true;
      head.replaceChildren(el("h2", { textContent: st.outline.title }), el("p", { className: "lead", textContent: st.outline.logline }));
      heroes.replaceChildren(el("h3", { textContent: "Твои герои" }), ...st.outline.characters.map((c) => {
        const frames = walkerFrames(c.appearance, `preview:${gameId}:${c.id}`).walk;
        const walker = pixel(frames[0], 3);
        const ctx = walker.getContext("2d")!;
        let i = 0;
        timers.push(window.setInterval(() => {
          i = (i + 1) % frames.length;
          ctx.clearRect(0, 0, walker.width, walker.height);
          ctx.drawImage(frames[i], 0, 0);
        }, 1000 / FPS.walk));
        return el("figure", { className: "hero-card" }, pixel(portraitCanvas(c.appearance, "neutral", `preview:${gameId}:${c.id}`), 2), walker,
          el("figcaption", {}, el("b", { textContent: c.name }), el("small", { textContent: { hero: "герой", companion: "компаньон", npc: "персонаж", antagonist: "антагонист" }[c.role] ?? c.role })));
      }));
    }
    if (st.status === "ready") {
      note.textContent = "";
      actions.replaceChildren(button("Играть ▸", () => { location.href = `/play/${gameId}`; }, "btn btn-primary"), publishToggle(gameId, st.published) ?? el("span"));
    }
    if (st.status === "failed") {
      note.textContent = "";
      const error = el("p", { className: "error", textContent: st.error ?? "Не получилось." });
      const retry = button("Попробовать ещё раз", () => void startGame(draft.get("brief"), error, retry), "btn btn-primary", !draft.get("brief"));
      actions.replaceChildren(error, retry, button("На главную", () => go("/"), "btn btn-ghost"));
    }
  };

  const poll = async () => {
    try {
      const st = await api.status(gameId);
      render(st);
      if (st.status !== "ready" && st.status !== "failed") timers.push(window.setTimeout(poll, 2000));
    } catch (e) {
      actions.replaceChildren(el("p", { className: "error", textContent: (e as ApiError).message }));
      timers.push(window.setTimeout(poll, 4000));
    }
  };
  void poll();
  window.addEventListener("popstate", () => timers.forEach((t) => clearTimeout(t)), { once: true });
}

// --- каталог готовых игр ---

const COVER_FRAME_MS = 520;

/** Обложка игры: фон стартовой локации, герой с компаньоном и главный враг напротив. Кадр стойки — frame. */
function drawCover(canvas: HTMLCanvasElement, c: GameCard, frame: number): void {
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(renderBackgroundCached(c), 0, 0);
  const { ref } = library.layout.walker;
  const feet = 87;
  const put = (img: HTMLCanvasElement, anchor: [number, number], x: number, flip: boolean) => {
    const left = Math.round(x - (flip ? img.width - anchor[0] : anchor[0]));
    const top = feet - anchor[1];
    ctx.save();
    if (flip) {
      ctx.scale(-1, 1);
      ctx.drawImage(img, -left - img.width, top);
    } else ctx.drawImage(img, left, top);
    ctx.restore();
  };
  const [hero, companion] = c.characters;
  if (companion) put(walkerFrames(companion.appearance, `cover:${c.id}:${companion.id}`).idle[(frame + 1) % 2], ref, 28, false);
  put(walkerFrames(hero.appearance, `cover:${c.id}:${hero.id}`).idle[frame % 2], ref, 48, false);
  if (c.enemy) {
    const a = c.enemy.appearance;
    if ("body" in a) {
      const frames = creatureMapFrames(a, `cover:${c.id}:${c.enemy.id}`);
      put(frames[frame % frames.length], [16, 31], 122, true);
    } else put(walkerFrames(a, `cover:${c.id}:${c.enemy.id}`).idle[frame % 2], ref, 122, true);
  }
}

const backgrounds = new Map<string, HTMLCanvasElement>();
function renderBackgroundCached(c: GameCard): HTMLCanvasElement {
  let bg = backgrounds.get(c.id);
  if (!bg) backgrounds.set(c.id, (bg = renderBackground(c.background, backgroundSeed(c.id, "cover")).toCanvas()));
  return bg;
}

function gameCard(c: GameCard, extra: Node | null = null): HTMLElement {
  const { w, h } = library.layout.background;
  const canvas = el("canvas", { className: "cover-art", width: w, height: h });
  let frame = 0;
  drawCover(canvas, c, frame);
  const timer = window.setInterval(() => {
    if (!canvas.isConnected && frame > 0) return window.clearInterval(timer);
    drawCover(canvas, c, ++frame);
  }, COVER_FRAME_MS);
  const meta = [c.est_minutes ? `≈${c.est_minutes} мин` : "", `${c.locations} локаций`, c.endings > 1 ? `${c.endings} концовки` : ""].filter(Boolean).join(" · ");
  const p = c.profile ?? {};
  const tags = [
    p.combat === "none" ? "Без боёв" : p.combat === "light" ? "Немного боёв" : "Тактические бои",
    { light: "лёгкие диалоги", rich: "живые диалоги", deep: "глубокие диалоги" }[p.dialogue ?? "rich"],
  ];
  const cover = el("a", { className: "cover", href: `/play/${c.id}` }, canvas,
    el("div", { className: "cover-title" }, el("h3", { textContent: c.title }), c.tone ? el("small", { textContent: c.tone }) : null));
  return el("article", { className: "game-card" }, cover,
    el("div", { className: "game-card-body" },
      el("div", { className: "tags" }, ...tags.map((t) => el("span", { className: "tag", textContent: t }))),
      el("p", { className: "logline", textContent: c.logline }),
      el("small", { className: "muted", textContent: meta }),
      el("div", { className: "row" }, el("a", { className: "btn btn-primary", href: `/play/${c.id}`, textContent: "Играть ▸" }), extra)));
}

/** Карточка демо-игры из бандла — каталог работает, даже если сервер недоступен. */
function demoCard(): GameCard {
  const g = demoGame as unknown as Game;
  const companion = (g.characters ?? []).find((c) => c.role === "companion");
  const boss = [...(g.enemies ?? [])].sort((a, b) => b.tier - a.tier)[0];
  return {
    id: "demo", title: g.meta.title, logline: g.meta.logline, tone: g.meta.tone, est_minutes: g.meta.est_minutes,
    locations: g.locations.length, endings: g.endings.length, characters: [g.hero, ...(companion ? [companion] : [])],
    background: g.locations.find((l) => l.id === g.start_location)!.background,
    enemy: boss ? { id: boss.id, name: boss.name, appearance: boss.appearance } : null, featured: true,
  };
}

export async function mountCatalog(root: HTMLElement): Promise<void> {
  document.title = "Готовые игры — Генератор RPG";
  const featured = el("div", { className: "game-grid" });
  const minePart = el("section", {});
  const community = el("div", { className: "game-grid" });
  root.replaceChildren(page(
    el("h1", { textContent: "Готовые игры" }),
    el("p", { className: "lead", textContent: "Сыграйте в игры из подборки или в истории, которые опубликовали другие игроки." }),
    el("h2", { textContent: "Подборка" }), featured,
    minePart,
    el("h2", { textContent: "Игры игроков" }), community,
  ));

  let catalog: { featured: GameCard[]; community: GameCard[] } = { featured: [demoCard()], community: [] };
  try {
    catalog = await api.catalog();
  } catch {
    featured.before(el("p", { className: "banner warn", textContent: "Сервер недоступен: показываем только демо-игру." }));
  }
  featured.replaceChildren(...catalog.featured.map((c) => gameCard(c)));
  const myIds = new Set(mine.list().map((g) => g.id));
  community.replaceChildren(...(catalog.community.length
    ? catalog.community.map((c) => gameCard(c, myIds.has(c.id) ? el("span", { className: "badge", textContent: "ваша" }) : null))
    : [el("p", { className: "muted", textContent: "Пока никто не опубликовал игру. Создайте свою и нажмите «Опубликовать в каталоге» — она появится здесь." })]));

  // мои игры: созданные в этом браузере; публикует и скрывает их только автор
  const own = mine.list().slice(0, 12);
  if (!own.length) return;
  const rows = await Promise.all(own.map(async (g) => {
    try {
      return { g, st: await api.status(g.id) };
    } catch {
      return { g, st: null };
    }
  }));
  const list = el("div", { className: "my-games" }, ...rows.filter((r) => r.st).map(({ g, st }) => {
    const title = st!.outline?.title ?? "Без названия";
    const state = st!.status === "ready" ? "" : st!.status === "failed" ? "не получилась" : "создаётся…";
    const actions = st!.status === "ready"
      ? el("div", { className: "row" }, el("a", { className: "btn", href: `/play/${g.id}`, textContent: "Играть" }), publishToggle(g.id, st!.published))
      : el("a", { className: "btn btn-ghost", href: `/progress/${g.id}`, textContent: "Открыть" });
    return el("div", { className: "my-game" }, el("div", {}, el("b", { textContent: title }), state ? el("small", { className: "muted", textContent: ` — ${state}` }) : null), actions);
  }));
  if (list.childElementCount) minePart.replaceChildren(el("h2", { textContent: "Мои игры" }), list);
}
