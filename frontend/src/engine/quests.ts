// Квесты: состояние не хранится, а вычисляется из условий (SPEC §5.3).

import type { Quest } from "../types/game";
import { check } from "./conditions";
import type { GameState } from "./state";
import type { Condition, World } from "./world";

export interface QuestView {
  quest: Quest;
  done: boolean[];
  complete: boolean;
}

export function questViews(state: GameState, world: World): QuestView[] {
  return world.quests
    .filter((q) => check(q.start as Condition | null, state, world))
    .map((quest) => {
      const done = quest.stages.map((s) => check(s.done as Condition, state, world));
      return { quest, done, complete: done.every(Boolean) };
    });
}

/** Сообщения о том, что изменилось в журнале между двумя снимками. */
export function questChanges(before: QuestView[], after: QuestView[]): string[] {
  const prev = new Map(before.map((v) => [v.quest.id, v]));
  const out: string[] = [];
  for (const v of after) {
    const old = prev.get(v.quest.id);
    if (!old) out.push(`Новый квест: ${v.quest.title}`);
    else if (v.complete && !old.complete) out.push(`Квест выполнен: ${v.quest.title}`);
    else if (v.done.filter(Boolean).length > old.done.filter(Boolean).length) out.push(`Журнал обновлён: ${v.quest.title}`);
  }
  return out;
}
