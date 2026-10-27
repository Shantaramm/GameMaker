// Главная, бриф и экран генерации (SPEC §11.1–11.3).

import { api, ApiError, draft, type Status } from "../api";
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

function page(...children: (Node | null)[]): HTMLElement {
  return el("main", { className: "site" }, ...children);
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
    const { game_id } = await api.create(brief);
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
      actions.replaceChildren(button("Играть ▸", () => { location.href = `/play/${gameId}`; }, "btn btn-primary"));
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
