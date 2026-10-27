// Выезжающие панели: инвентарь и экипировка, торговец, журнал квестов.

import { buy, canSell, equip, isEquipped, nextLevelXp, sell, sellPrice, spendSkillPoint, unequip, useItem } from "../engine/effects";
import { SKILL_CAP, SKILL_GROUPS } from "../engine/inner";
import type { QuestView } from "../engine/quests";
import { count, effective, type GameState, skillValue } from "../engine/state";
import { SLOTS, type Slot, type World } from "../engine/world";
import { iconCanvas } from "../pixel/tiles";
import type { Item, Shop } from "../types/game";
import { bar, button, el, pixel } from "./dom";

const SLOT_NAMES: Record<Slot, string> = { hand: "В руке", body: "Одежда", trinket: "Аксессуар" };

function icon(item: Item, scale = 2): HTMLCanvasElement {
  return pixel(iconCanvas(item.icon, item.value_tier), scale);
}

function bonusText(item: Item): string {
  const b = item.equip?.bonus;
  if (!b) return "";
  const parts = [["атака", b.attack], ["защита", b.defense], ["фокус", b.focus], ["здоровье", b.hp]]
    .filter(([, v]) => v)
    .map(([n, v]) => `${n} ${(v as number) > 0 ? "+" : ""}${v}`);
  for (const [k, v] of Object.entries(b.skills ?? {})) if (v) parts.push(`${skillLabel(k)} ${v > 0 ? "+" : ""}${v}`);
  return parts.join(", ");
}

// названия навыков текущей игры для подписей бонусов вещей; заполняет skillsView/inventoryView
let skillLabel: (key: string) => string = (k) => k;
export function setSkillNames(world: World): void {
  skillLabel = (k) => world.skillName(k);
}

export class Sheet {
  readonly root = el("div", { className: "sheet hidden" });
  private body = el("div", { className: "sheet-body" });
  private title = el("h2", {});
  private onClose: (() => void) | null = null;

  constructor() {
    this.root.append(el("div", { className: "sheet-head" }, this.title, button("✕", () => this.close(), "btn btn-ghost sheet-close")), this.body);
  }

  open(title: string, content: Node[], onClose: () => void): void {
    this.title.textContent = title;
    this.body.replaceChildren(...content);
    this.onClose = onClose;
    this.root.classList.remove("hidden");
  }

  replace(content: Node[]): void {
    this.body.replaceChildren(...content);
  }

  get isOpen(): boolean {
    return !this.root.classList.contains("hidden");
  }

  close(): void {
    this.root.classList.add("hidden");
    const cb = this.onClose;
    this.onClose = null;
    cb?.();
  }
}

/** Лист внутренних навыков (§5.10): 4 группы по 2, значение с бонусом вещей, «+» за очко навыка. */
export function skillsView(state: GameState, world: World, rerender: () => void): HTMLElement {
  const groups = SKILL_GROUPS.map(([group, keys]) => el("div", { className: "skill-group" },
    el("div", { className: "skill-group-name", textContent: group }),
    ...keys.map((key) => {
      const base = state.inner[key] ?? 0;
      const value = skillValue(state, world, key);
      const info = world.skillNames.get(key);
      const plus = state.skillPoints > 0 && base < SKILL_CAP
        ? button("+", () => { spendSkillPoint(state, world, key); rerender(); }, "btn btn-small skill-plus") : null;
      return el("div", { className: "skill" },
        el("div", { className: "skill-head" },
          el("b", { textContent: info?.name ?? key }),
          el("span", { className: "skill-value", textContent: value !== base ? `${value} (${base}${value > base ? "+" : ""}${value - base})` : String(value) }),
          plus),
        el("small", { textContent: info?.description ?? "" }));
    })));
  return el("div", { className: "skills-sheet" },
    state.skillPoints > 0 ? el("p", { className: "skill-points", textContent: `Свободных очков навыков: ${state.skillPoints}. Каждое делает проверки этого навыка легче.` }) : null,
    el("div", { className: "skill-groups" }, ...groups));
}

export function inventoryView(state: GameState, world: World, rerender: () => void, notify: (m: string[]) => void): Node[] {
  const eff = effective(state, world);
  const next = nextLevelXp(state, world);
  const stats = el("div", { className: "inv-stats" },
    el("div", {}, `Уровень ${state.level}`, next ? bar(state.xp, next, "xp") : el("span", { textContent: " (макс.)" })),
    el("div", {}, "Здоровье", bar(state.hp, eff.maxHp, "hp")),
    el("div", {}, "Дух", bar(state.morale, eff.maxMorale, "morale")),
    ...(world.noCombat ? [] : [
      el("div", {}, "Фокус", bar(state.focus, eff.maxFocus, "focus")),
      el("div", { className: "inv-nums", textContent: `Атака ${eff.attack} · Защита ${eff.defense} · Золото ${state.gold}` })]));

  const slots = el("div", { className: "inv-slots" }, ...SLOTS.map((slot) => {
    const item = world.items.get(state.equipment[slot] ?? "");
    return el("div", { className: "inv-slot" }, el("div", { className: "slot-name", textContent: SLOT_NAMES[slot] }),
      item ? icon(item, 3) : el("div", { className: "slot-empty" }),
      el("div", { className: "slot-item", textContent: item?.name ?? "—" }),
      item ? button("Снять", () => { unequip(state, world, slot); rerender(); }, "btn btn-small") : null);
  }));

  const detail = el("div", { className: "inv-detail", textContent: "Выберите предмет." });
  const list = el("div", { className: "inv-list" });
  for (const [id, n] of Object.entries(state.inventory)) {
    const item = world.items.get(id);
    if (!item || n <= 0) continue;
    const row = el("button", { className: `inv-item${isEquipped(state, id) ? " equipped" : ""}` }, icon(item),
      el("span", { textContent: `${item.name}${n > 1 ? ` ×${n}` : ""}` }));
    row.addEventListener("click", () => {
      const actions: Node[] = [];
      if (item.kind === "consumable") actions.push(button("Использовать", () => { notify(useItem(state, world, id)); rerender(); }, "btn btn-primary"));
      if (item.equip) actions.push(isEquipped(state, id)
        ? button("Снять", () => { unequip(state, world, item.equip!.slot as Slot); rerender(); }, "btn")
        : button("Надеть", () => { equip(state, world, id); rerender(); }, "btn btn-primary"));
      detail.replaceChildren(el("b", { textContent: item.name }), el("p", { textContent: item.description }),
        ...(item.equip ? [el("p", { className: "bonus", textContent: `${SLOT_NAMES[item.equip.slot as Slot]}: ${bonusText(item)}` })] : []),
        el("div", { className: "row" }, ...actions));
    });
    list.append(row);
  }
  if (!list.children.length) list.append(el("p", { className: "muted", textContent: "Пусто." }));
  const skills = state.skills.map((id) => world.skills.get(id)).filter(Boolean)
    .map((s) => el("li", {}, el("b", { textContent: s!.name }), ` (${s!.cost_focus} фок.) — ${s!.description}`));
  return [stats, el("h3", { textContent: "Внутренние навыки" }), skillsView(state, world, rerender), slots, el("h3", { textContent: "Вещи" }), list, detail,
    ...(skills.length ? [el("h3", { textContent: "Боевые навыки" }), el("ul", { className: "skills" }, ...skills)] : [])];
}

export function shopView(shop: Shop, state: GameState, world: World, rerender: () => void): Node[] {
  const buyRows = shop.items.map((id) => {
    const item = world.items.get(id)!;
    const price = item.price ?? 0;
    return el("div", { className: "shop-row" }, icon(item),
      el("div", { className: "shop-name" }, el("b", { textContent: item.name }), el("small", { textContent: item.equip ? bonusText(item) : item.description })),
      button(`${price} з.`, () => { buy(state, world, id); rerender(); }, "btn btn-small", state.gold < price));
  });
  const sellRows = shop.buys
    ? Object.keys(state.inventory).filter((id) => canSell(state, world, id)).map((id) => {
      const item = world.items.get(id)!;
      return el("div", { className: "shop-row" }, icon(item),
        el("div", { className: "shop-name" }, el("b", { textContent: `${item.name} ×${count(state, id)}` })),
        button(`+${sellPrice(world, id)} з.`, () => { sell(state, world, id); rerender(); }, "btn btn-small"));
    })
    : [];
  return [el("p", { className: "gold", textContent: `Ваше золото: ${state.gold}` }), el("h3", { textContent: "Купить" }), ...buyRows,
    ...(shop.buys ? [el("h3", { textContent: "Продать" }), ...(sellRows.length ? sellRows : [el("p", { className: "muted", textContent: "Нечего продать." })])] : [])];
}

export function journalView(quests: QuestView[]): Node[] {
  if (!quests.length) return [el("p", { className: "muted", textContent: "Пока нет заданий." })];
  const sorted = [...quests].sort((a, b) => Number(a.complete) - Number(b.complete) || Number(b.quest.main ?? false) - Number(a.quest.main ?? false));
  return sorted.map((v) => {
    const firstOpen = v.done.indexOf(false);
    const stages = v.quest.stages.map((s, i) => {
      if (v.done[i]) return el("li", { className: "done", textContent: `✓ ${s.text}` });
      if (i === firstOpen) return el("li", { className: "current", textContent: `▸ ${s.text}` });
      return null;
    }).filter((x): x is HTMLLIElement => !!x);
    return el("div", { className: `quest${v.complete ? " complete" : ""}` },
      el("b", { textContent: `${v.quest.title}${v.quest.main ? " · основной" : ""}${v.complete ? " — выполнен" : ""}` }),
      el("ul", {}, ...stages));
  });
}
