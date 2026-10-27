// Верхняя панель, всплывающие уведомления и полноэкранные экраны (начало, концовка, поражение).

import { effective, type GameState } from "../engine/state";
import type { World } from "../engine/world";
import type { Ending } from "../types/game";
import { bar, button, el } from "./dom";

export class Hud {
  readonly root = el("div", { className: "hud" });
  private stats = el("div", { className: "hud-stats" });
  private place = el("div", { className: "hud-place" });

  constructor(onInventory: () => void, onJournal: () => void) {
    this.root.append(this.stats, this.place,
      el("div", { className: "hud-buttons" }, button("Вещи", onInventory, "btn btn-small"), button("Журнал", onJournal, "btn btn-small")));
  }

  update(state: GameState, world: World): void {
    const eff = effective(state, world);
    this.stats.replaceChildren(
      el("span", { className: "hud-level", textContent: `Ур.${state.level}` }),
      bar(state.hp, eff.maxHp, "hp"),
      bar(state.focus, eff.maxFocus, "focus", false),
      el("span", { className: "hud-gold", textContent: `◆${state.gold}` }));
    this.place.textContent = world.location(state.location).title;
  }
}

export class Toasts {
  readonly root = el("div", { className: "toasts" });

  show(messages: string[]): void {
    for (const m of messages) {
      const t = el("div", { className: "toast", textContent: m });
      this.root.append(t);
      setTimeout(() => t.classList.add("out"), 2600);
      setTimeout(() => t.remove(), 3100);
    }
  }
}

function screen(...children: (Node | null)[]): HTMLElement {
  return el("div", { className: "screen" }, el("div", { className: "screen-box" }, ...children.filter((c): c is Node => c !== null)));
}

export function titleScreen(world: World, hasSave: boolean, onContinue: () => void, onNew: () => void): HTMLElement {
  const m = world.game.meta;
  return screen(
    el("h1", { textContent: m.title }),
    el("p", { className: "logline", textContent: m.logline }),
    el("p", { className: "muted", textContent: `~${m.est_minutes} минут · ${m.tone}` }),
    el("div", { className: "row" },
      hasSave ? button("Продолжить", onContinue, "btn btn-primary") : null,
      button(hasSave ? "Новая игра" : "Начать", onNew, hasSave ? "btn" : "btn btn-primary")),
    el("p", { className: "hint", textContent: "Тап по месту — идти, по персонажу или предмету — взаимодействовать. Клавиши: A/D, W/S у лестницы, E — действие." }),
  );
}

export function endingScreen(ending: Ending, shareUrl: string, onRestart: () => void, extra: Node | null = null): HTMLElement {
  const status = el("p", { className: "muted" });
  return screen(
    el("p", { className: `ending-kind ${ending.kind}`, textContent: { good: "Хорошая концовка", neutral: "Концовка", bad: "Горькая концовка" }[ending.kind] }),
    el("h1", { textContent: ending.title }),
    el("p", { className: "logline", textContent: ending.text }),
    el("div", { className: "row" },
      button("Поделиться", async () => {
        try {
          await navigator.clipboard.writeText(shareUrl);
          status.textContent = "Ссылка скопирована.";
        } catch {
          status.textContent = shareUrl;
        }
      }, "btn btn-primary"),
      button("Сыграть заново", onRestart, "btn")),
    status,
    extra,
  );
}

export function gameOverScreen(onLoad: () => void, onRestart: () => void): HTMLElement {
  return screen(
    el("h1", { textContent: "Поражение" }),
    el("p", { className: "logline", textContent: "Туман сомкнулся. Но история ещё не окончена." }),
    el("div", { className: "row" }, button("Вернуться к сохранению", onLoad, "btn btn-primary"), button("Начать заново", onRestart, "btn")),
  );
}
