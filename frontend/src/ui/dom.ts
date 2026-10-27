// Мелкие помощники DOM для игрового интерфейса.

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K, props: Record<string, unknown> = {}, ...children: (Node | string | null | false)[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props) as HTMLElementTagNameMap[K];
  node.append(...children.filter((c): c is Node | string => c !== null && c !== false));
  return node;
}

export function button(text: string, onClick: () => void, className = "btn", disabled = false): HTMLButtonElement {
  const b = el("button", { className, textContent: text, disabled });
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  return b;
}

export function bar(value: number, max: number, kind: "hp" | "focus" | "xp", label = true): HTMLElement {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return el("div", { className: `bar bar-${kind}` },
    el("div", { className: "bar-fill", style: `width:${pct}%` }),
    label ? el("span", { className: "bar-text", textContent: `${Math.max(0, value)}/${max}` }) : null);
}

/** Пиксельная картинка с целочисленным масштабом. */
export function pixel(canvas: HTMLCanvasElement, scale: number, className = "pixel"): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = canvas.width;
  c.height = canvas.height;
  c.getContext("2d")!.drawImage(canvas, 0, 0);
  c.className = className;
  c.style.width = `${canvas.width * scale}px`;
  c.style.height = `${canvas.height * scale}px`;
  return c;
}

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
