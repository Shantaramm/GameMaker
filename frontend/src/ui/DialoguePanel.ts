// Диалоги в стиле Disco Elysium (SPEC §11, §5.10): лента реплик, портрет говорящего, пронумерованные варианты,
// недоступные — серые с условием в квадратных скобках; голоса навыков, проверки с шансом и броском кубиков.

import type { ChoiceView, ChooseResult, DialogueRunner, PassiveView } from "../engine/runtime";
import { NARRATOR, type World } from "../engine/world";
import { portraitCanvas, type Emotion } from "../pixel/sprite";
import { button, el, pixel, sleep } from "./dom";

const DICE = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

function checkLabel(c: ChoiceView): string {
  if (!c.check) return "";
  const k = c.check;
  if (k.status === "passed") return `[${k.name} · пройдено] `;
  return `[${k.name} · ${k.difficulty} ${k.target} — ${Math.round(k.chance * 100)}%] `;
}

/** Портрет крупнее на больших экранах, мельче на телефоне. */
function portraitScale(): number {
  const h = window.innerHeight;
  return window.innerWidth <= 640 ? 2 : h >= 1300 ? 5 : h >= 900 ? 4 : 3;
}

export class DialoguePanel {
  readonly root = el("div", { className: "dlg hidden" });
  private portrait = el("div", { className: "dlg-portrait" });
  private log = el("div", { className: "dlg-log" });
  private actions = el("div", { className: "dlg-actions" });
  private keyHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor(private world: World, private notify: (m: string[]) => void) {
    this.root.append(this.portrait, el("div", { className: "dlg-main" }, this.log, this.actions));
  }

  open(runner: DialogueRunner): Promise<void> {
    this.log.replaceChildren();
    this.root.classList.remove("hidden");
    return new Promise((resolve) => {
      const finish = (messages: string[]) => {
        this.root.classList.add("hidden");
        if (this.keyHandler) window.removeEventListener("keydown", this.keyHandler);
        this.keyHandler = null;
        if (messages.length) this.notify(messages);
        resolve();
      };
      const show = () => {
        const line = runner.current();
        for (const p of line.passives) this.addPassive(p);
        this.addLine(line.speaker, line.text, line.emotion);
        this.actions.replaceChildren();
        const keys: Record<string, () => void> = {};
        if (!line.choices.length) {
          const next = () => {
            runner.advance();
            if (runner.done) finish([]);
            else show();
          };
          this.actions.append(button("Далее ▸", next, "btn btn-next"));
          keys[" "] = keys["enter"] = next;
        } else {
          const list = el("ol", { className: "dlg-choices" });
          line.choices.forEach((c, i) => {
            let picked = false;
            const pick = async () => {
              if (!c.available || picked) return;
              picked = true;
              this.actions.querySelectorAll("button").forEach((b) => ((b as HTMLButtonElement).disabled = true));
              this.addLine(this.world.game.hero.id, c.text, "neutral", true);
              const result = runner.choose(i);
              if (result.roll) await this.showRoll(result);
              if (runner.done) finish(result.messages);
              else {
                for (const m of result.messages) this.log.append(el("p", { className: "sys", textContent: m }));
                show();
              }
            };
            const label = `${i + 1}. ${checkLabel(c)}${c.text}${c.hint ? ` [${c.hint}]` : ""}`;
            const cls = `choice${c.available ? "" : " locked"}${c.check ? (c.check.red ? " check red" : " check") : ""}`;
            list.append(el("li", {}, button(label, () => void pick(), cls, !c.available)));
            keys[String(i + 1)] = pick;
          });
          this.actions.append(list);
        }
        if (this.keyHandler) window.removeEventListener("keydown", this.keyHandler);
        this.keyHandler = (e) => {
          const fn = keys[e.key.toLowerCase()];
          if (fn) {
            e.preventDefault();
            fn();
          }
        };
        window.addEventListener("keydown", this.keyHandler);
        this.log.scrollTop = this.log.scrollHeight;
      };
      show();
    });
  }

  /** Пассивная проверка: голос навыка вмешивается сам, без броска. */
  private addPassive(p: PassiveView): void {
    this.log.append(el("p", { className: "line voice passive" },
      el("b", { className: "who", textContent: p.name.toUpperCase() }), el("small", { textContent: ` [${p.difficulty}: успех] ` }), "— ", p.text));
  }

  /** Бросок 2d6 + навык: кубики крутятся, затем итог «Успех» или «Провал». */
  private async showRoll(result: ChooseResult): Promise<void> {
    const r = result.roll!;
    const dice = el("span", { className: "dice rolling", textContent: "⚀ ⚀" });
    const line = el("p", { className: "line roll" }, dice, el("span", { textContent: ` ${r.name}: ` }));
    this.log.append(line);
    this.log.scrollTop = this.log.scrollHeight;
    for (let i = 0; i < 6; i++) {
      dice.textContent = `${DICE[1 + Math.floor(Math.random() * 6)]} ${DICE[1 + Math.floor(Math.random() * 6)]}`;
      await sleep(70);
    }
    dice.classList.remove("rolling");
    dice.textContent = `${DICE[r.dice[0]]} ${DICE[r.dice[1]]}`;
    line.append(
      `${r.dice[0]} + ${r.dice[1]} + ${r.value} = ${r.dice[0] + r.dice[1] + r.value} против ${r.target} — `,
      el("b", { className: r.success ? "ok" : "fail", textContent: r.success ? "УСПЕХ" : "ПРОВАЛ" }));
    this.log.scrollTop = this.log.scrollHeight;
    await sleep(500);
  }

  private addLine(speaker: string, text: string, emotion: string, isChoice = false): void {
    if (speaker.startsWith("skill:")) {
      // внутренний голос героя — без портрета, своим цветом
      this.log.append(el("p", { className: "line voice" }, el("b", { className: "who", textContent: this.world.skillName(speaker.slice(6)).toUpperCase() }), " — ", text));
      return;
    }
    if (speaker === NARRATOR) {
      this.portrait.replaceChildren();
      this.portrait.classList.add("empty");
      this.log.append(el("p", { className: "line narrator", textContent: text }));
      return;
    }
    const c = this.world.characters.get(speaker);
    const name = c?.name ?? speaker;
    if (c) {
      this.portrait.classList.remove("empty");
      this.portrait.replaceChildren(pixel(portraitCanvas(c.appearance, emotion as Emotion, c.id), portraitScale()), el("div", { className: "dlg-name", textContent: name }));
    }
    const hero = speaker === this.world.game.hero.id;
    this.log.append(el("p", { className: `line${hero ? " hero" : ""}` },
      el("b", { className: "who", textContent: name.toUpperCase() }), " — ", isChoice ? `«${text}»` : text));
  }
}
