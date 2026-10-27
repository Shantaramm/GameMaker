// Диалоги в стиле Disco Elysium (SPEC §11): лента реплик, портрет говорящего, пронумерованные варианты,
// недоступные — серые с условием в квадратных скобках.

import type { DialogueRunner } from "../engine/runtime";
import { NARRATOR, type World } from "../engine/world";
import { portraitCanvas, type Emotion } from "../pixel/sprite";
import { button, el, pixel } from "./dom";

export class DialoguePanel {
  readonly root = el("div", { className: "dlg hidden" });
  private portrait = el("div", { className: "dlg-portrait" });
  private log = el("div", { className: "dlg-log" });
  private actions = el("div", { className: "dlg-actions" });
  private keyHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor(private world: World, private notify: (m: string[]) => void) {
    this.root.append(this.portrait, this.log, this.actions);
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
            const pick = () => {
              if (!c.available) return;
              this.addLine(this.world.game.hero.id, c.text, "neutral", true);
              const messages = runner.choose(i);
              if (runner.done) finish(messages);
              else {
                for (const m of messages) this.log.append(el("p", { className: "sys", textContent: m }));
                show();
              }
            };
            const label = `${i + 1}. ${c.text}${c.hint ? ` [${c.hint}]` : ""}`;
            list.append(el("li", {}, button(label, pick, c.available ? "choice" : "choice locked", !c.available)));
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

  private addLine(speaker: string, text: string, emotion: string, isChoice = false): void {
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
      this.portrait.replaceChildren(pixel(portraitCanvas(c.appearance, emotion as Emotion, c.id), 3), el("div", { className: "dlg-name", textContent: name }));
    }
    const hero = speaker === this.world.game.hero.id;
    this.log.append(el("p", { className: `line${hero ? " hero" : ""}` },
      el("b", { className: "who", textContent: name.toUpperCase() }), " — ", isChoice ? `«${text}»` : text));
  }
}
