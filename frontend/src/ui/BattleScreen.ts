// Экран пошагового боя: враги с полосами HP, панель героя, действия, лог, вспышка и тряска при ударе.

import type { Battle, BattleEvent } from "../engine/battle";
import { count, effective } from "../engine/state";
import type { World } from "../engine/world";
import { renderBackground, backgroundSeed } from "../pixel/background";
import { CREATURE_SCALE, creatureCanvas, portraitCanvas } from "../pixel/sprite";
import type { BackgroundSpec } from "../types/game";
import { bar, button, el, pixel, sleep } from "./dom";

export class BattleScreen {
  readonly root = el("div", { className: "battle hidden" });

  constructor(private world: World) {}

  open(battle: Battle, background: BackgroundSpec, locationId: string): Promise<"win" | "lose" | "fled"> {
    const world = this.world;
    const state = battle.state;
    let target = battle.alive[0];
    let busy = false;
    let submenu: "skills" | "items" | null = null;
    const bg = pixel(renderBackground({ ...background, props: [] }, backgroundSeed(world.id, locationId)).toCanvas(), 1, "pixel battle-bg");
    const foesRow = el("div", { className: "battle-foes" });
    const heroBox = el("div", { className: "battle-hero" });
    const log = el("div", { className: "battle-log" });
    const actions = el("div", { className: "battle-actions" });
    this.root.replaceChildren(bg, foesRow, el("div", { className: "battle-panel" }, heroBox, log, actions));
    this.root.classList.remove("hidden");

    const foeNodes = battle.foes.map((f, i) => {
      const e = world.enemies.get(f.enemyId)!;
      const art = "body" in e.appearance
        ? pixel(creatureCanvas(e.appearance, e.id), Math.round(2 * CREATURE_SCALE[e.appearance.size]))
        : pixel(portraitCanvas(e.appearance, "angry", e.id), 2);
      const hp = el("div", { className: "foe-hp" });
      const node = el("div", { className: "foe" }, art, el("div", { className: "foe-name", textContent: f.name }), hp);
      node.addEventListener("click", () => {
        if (f.hp > 0) {
          target = i;
          render();
        }
      });
      foesRow.append(node);
      return { node, hp };
    });

    const heroPortrait = pixel(portraitCanvas(world.game.hero.appearance, "angry", world.game.hero.id), 2);

    const render = () => {
      const eff = effective(state, world);
      battle.foes.forEach((f, i) => {
        foeNodes[i].hp.replaceChildren(bar(Math.max(0, f.hp), f.maxHp, "hp"));
        foeNodes[i].node.classList.toggle("dead", f.hp <= 0);
        foeNodes[i].node.classList.toggle("target", i === target && f.hp > 0 && battle.alive.length > 1);
      });
      heroBox.replaceChildren(heroPortrait, el("div", { className: "hero-bars" },
        el("div", { className: "hero-name", textContent: world.game.hero.name }),
        bar(state.hp, eff.maxHp, "hp"), bar(state.focus, eff.maxFocus, "focus")));
      if (battle.result && !busy) finish();
      else menu(submenu);
    };

    const say = (text: string, cls = "") => {
      log.append(el("p", { className: cls, textContent: text }));
      while (log.children.length > 5) log.firstChild!.remove();
    };

    const play = async (events: BattleEvent[]) => {
      busy = true;
      menu();
      for (const ev of events) {
        say(ev.text, ev.actor === "hero" ? "you" : "them");
        const node = ev.target === "hero" ? heroBox : typeof ev.target === "number" ? foeNodes[ev.target].node : null;
        if (node && ev.amount !== 0) {
          node.classList.remove("hit");
          void node.offsetWidth;
          node.classList.add(ev.amount > 0 ? "hit" : "heal");
        }
        render();
        await sleep(380);
      }
      if (battle.alive.length && battle.foes[target]?.hp <= 0) target = battle.alive[0];
      busy = false;
      submenu = null;
      render();
    };

    let resolveFn: (r: "win" | "lose" | "fled") => void;
    const finish = () => {
      const r = battle.result!;
      const text = r === "win" ? "Победа!" : r === "lose" ? "Поражение…" : "Вы сбежали.";
      actions.replaceChildren(el("div", { className: `battle-result ${r}`, textContent: text }),
        button("Продолжить", () => {
          this.root.classList.add("hidden");
          resolveFn(r);
        }, "btn btn-primary"));
    };

    const menu = (sub: "skills" | "items" | null = null) => {
      submenu = sub;
      actions.replaceChildren();
      if (battle.result) return; // пока доигрывается последний ход, кнопок нет; потом finish() покажет итог
      if (sub === "skills") {
        for (const id of state.skills) {
          const s = world.skills.get(id);
          if (!s) continue;
          actions.append(button(`${s.name} (${s.cost_focus} фок.)`, () => play(battle.skill(id, target)), "btn", busy || !battle.canUseSkill(id)));
        }
        actions.append(button("Назад", () => menu(), "btn btn-ghost"));
        return;
      }
      if (sub === "items") {
        for (const [id, n] of Object.entries(state.inventory)) {
          const item = world.items.get(id);
          if (item?.kind !== "consumable" || n <= 0) continue;
          actions.append(button(`${item.name} ×${count(state, id)}`, () => play(battle.item(id, target)), "btn", busy));
        }
        actions.append(button("Назад", () => menu(), "btn btn-ghost"));
        return;
      }
      const hasItems = Object.keys(state.inventory).some((id) => world.items.get(id)?.kind === "consumable");
      actions.append(
        button("Атака", () => play(battle.attack(target)), "btn btn-primary", busy),
        button("Навык", () => menu("skills"), "btn", busy || !state.skills.length),
        button("Предмет", () => menu("items"), "btn", busy || !hasItems),
        button("Побег", () => play(battle.flee()), "btn", busy),
      );
    };

    render();
    say(`На вас нападают: ${battle.foes.map((f) => f.name).join(", ")}.`);
    return new Promise((resolve) => (resolveFn = resolve));
  }
}
