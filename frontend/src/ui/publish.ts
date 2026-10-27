// Публикация игры в каталоге «Готовые игры». Без неё игра доступна только по ссылке.

import { api, ApiError, mine } from "../api";
import { button, el } from "./dom";

/**
 * Кнопка «Опубликовать в каталоге» / «Скрыть из каталога» — только у автора (секрет есть в этом браузере).
 * Без публикации игра доступна лишь по ссылке.
 */
export function publishToggle(gameId: string, published: boolean | null = null): HTMLElement | null {
  const me = mine.get(gameId);
  if (!me) return null;
  const box = el("span", { className: "publish" });
  const note = el("small", { className: "muted" });
  let state = published;
  const render = () => {
    const b = button(state ? "Скрыть из каталога" : "Опубликовать в каталоге", async () => {
      b.disabled = true;
      try {
        state = (await api.publish(gameId, me.token, !state)).published;
        note.textContent = state ? "Игра в каталоге «Готовые игры»." : "Игра доступна только по ссылке.";
      } catch (e) {
        note.textContent = (e as ApiError).message;
      }
      render();
    }, state ? "btn btn-ghost" : "btn", state === null);
    box.replaceChildren(b, note);
  };
  render();
  if (state === null) {
    void api.status(gameId).then((st) => {
      state = st.published;
      render();
    }).catch(() => box.remove());
  }
  return box;
}
