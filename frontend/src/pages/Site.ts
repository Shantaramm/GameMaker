// Главная, бриф, экран генерации (SPEC §11.1–11.3) и каталог готовых игр.

import { api, ApiError, draft, type GameCard, mine, type Status } from "../api";
import { publishToggle } from "../ui/publish";
import demoGame from "../data/demo_game.json";
import { portraitCanvas } from "../pixel/sprite";
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
  return el("p", { className: "banner", textContent: "Демо-режим: GigaChat ещё не подключён, поэтому любая идея превратится в демо-игру «Погасший маяк». Весь путь — бриф, генерация, игра, ссылка — работает по-настоящему." });
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

async function startGame(brief: string, error: HTMLElement, b: HTMLButtonElement): Promise<void> {
  const done = busyButton(b, "Отправляем…");
  try {
    const { game_id, owner_token } = await api.create(brief);
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
      const brief = await api.brief(idea.value.trim());
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

function gameCard(c: GameCard, extra: Node | null = null): HTMLElement {
  const faces = el("div", { className: "card-faces" }, ...c.characters.map((ch) =>
    pixel(portraitCanvas(ch.appearance, "neutral", `card:${c.id}:${ch.id}`), ch.role === "hero" ? 2 : 1)));
  const meta = [c.est_minutes ? `≈${c.est_minutes} мин` : "", `${c.locations} локаций`, c.endings > 1 ? `${c.endings} концовки` : ""].filter(Boolean).join(" · ");
  const play = el("a", { className: "btn btn-primary", href: `/play/${c.id}`, textContent: "Играть ▸" });
  return el("article", { className: "game-card" }, faces,
    el("div", { className: "game-card-body" },
      el("h3", { textContent: c.title }),
      el("p", { className: "logline", textContent: c.logline }),
      el("small", { className: "muted", textContent: [c.tone, meta].filter(Boolean).join(" · ") }),
      el("div", { className: "row" }, play, extra)));
}

/** Карточка демо-игры из бандла — каталог работает, даже если сервер недоступен. */
function demoCard(): GameCard {
  const g = demoGame as unknown as { meta: { title: string; logline: string; tone: string; est_minutes: number }; locations: unknown[]; endings: unknown[]; hero: GameCard["characters"][number]; characters: GameCard["characters"] };
  const companion = g.characters.find((c) => c.role === "companion");
  return {
    id: "demo", title: g.meta.title, logline: g.meta.logline, tone: g.meta.tone, est_minutes: g.meta.est_minutes,
    locations: g.locations.length, endings: g.endings.length, characters: [g.hero, ...(companion ? [companion] : [])], featured: true,
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
