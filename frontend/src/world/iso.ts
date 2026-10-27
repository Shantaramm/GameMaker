// Изометрическое поле тактического боя (SPEC §5.9). Поле строит бэкенд (arenas.py) — здесь только рисуем.
// Клетка (x, y) уходит по экрану: x — вправо-вниз, y — влево-вниз. Верх клетки — ромб TW×TH, высота — HS за уровень.

import type { Arena, BackgroundSpec } from "../types/game";
import { propCanvas, tileCanvas } from "../pixel/tiles";
import type { Cell } from "../engine/tactics";

export const TW = 32;
export const TH = 16;
export const HS = 8;
const BASE = 6;        // толщина «плиты» под полем
const MARGIN = 8;
const HEADROOM = 46;   // место над верхним рядом под спрайты

export interface IsoUnit {
  id: string;
  x: number;           // дробные во время движения
  y: number;
  facing: Cell;
  side: "party" | "enemy";
  frames: HTMLCanvasElement[];
  anchor: [number, number];
  hp: number;
  maxHp: number;
  alive: boolean;
  hitAt: number;
  lunge: Cell | null;  // куда тянется удар
  lungeAt: number;
  flip: boolean;
}

export type Highlight = "move" | "attack" | "range" | "selected" | "target";

const HIGHLIGHT: Record<Highlight, [string, string]> = {
  move: ["rgba(80, 170, 255, 0.32)", "rgba(140, 200, 255, 0.85)"],
  attack: ["rgba(255, 70, 50, 0.45)", "rgba(255, 140, 120, 0.95)"],
  range: ["rgba(255, 90, 60, 0.14)", "rgba(255, 120, 90, 0.35)"],
  selected: ["rgba(255, 220, 90, 0.25)", "rgba(255, 225, 110, 1)"],
  target: ["rgba(255, 220, 90, 0.4)", "rgba(255, 240, 160, 1)"],
};

/** Пиксели картинки через отдельный холст: так браузер не ругается на чтение из рабочих холстов. */
function pixels(img: HTMLCanvasElement): Uint8ClampedArray {
  const probe = document.createElement("canvas");
  probe.width = img.width;
  probe.height = img.height;
  const ctx = probe.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0);
  return ctx.getImageData(0, 0, img.width, img.height).data;
}

function shade(canvas: HTMLCanvasElement | null, k: number, fallback: string): string {
  if (!canvas) return fallback;
  const data = pixels(canvas);
  let r = 0, g = 0, b = 0, n = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue;
    r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
  }
  if (!n) return fallback;
  return `rgb(${Math.round((r / n) * k)}, ${Math.round((g / n) * k)}, ${Math.round((b / n) * k)})`;
}

export class IsoView {
  readonly canvas = document.createElement("canvas");
  readonly ctx: CanvasRenderingContext2D;
  readonly heights: number[][];
  readonly blocked: Set<string>;
  private readonly top: HTMLCanvasElement | null;
  private readonly left: string;
  private readonly right: string;
  private readonly props = new Map<string, { canvas: HTMLCanvasElement; anchor: [number, number] }>();
  private readonly ox: number;
  private readonly oy: number;

  constructor(readonly arena: Arena, theme: string, background: BackgroundSpec) {
    const { width: w, height: h } = arena;
    this.heights = arena.cells.map((row) => [...row].map((c) => (c === "#" ? 0 : Number(c))));
    this.blocked = new Set(arena.cells.flatMap((row, y) => [...row].flatMap((c, x) => (c === "#" ? [`${x},${y}`] : []))));
    this.canvas.width = ((w + h) * TW) / 2 + MARGIN * 2;
    this.canvas.height = ((w + h) * TH) / 2 + 2 * HS + BASE + HEADROOM + MARGIN;
    this.canvas.className = "iso";
    this.ctx = this.canvas.getContext("2d")!;
    this.ctx.imageSmoothingEnabled = false;
    this.ox = (h * TW) / 2 + MARGIN;
    this.oy = HEADROOM + 2 * HS;
    const { mood_palette: mood, time } = background;
    this.top = tileCanvas(theme, "floor", mood, time);
    const fill = tileCanvas(theme, "fill", mood, time) ?? this.top;
    this.left = shade(fill, 0.72, "#4a4058");
    this.right = shade(fill, 0.52, "#342c40");
    for (const p of arena.props ?? []) this.props.set(`${p.x},${p.y}`, propCanvas(p.id, mood, time));
  }

  height(x: number, y: number): number {
    const cx = Math.max(0, Math.min(this.arena.width - 1, Math.round(x)));
    const cy = Math.max(0, Math.min(this.arena.height - 1, Math.round(y)));
    return this.heights[cy][cx];
  }

  /** Верхняя вершина ромба клетки (логические пиксели холста). */
  cellTop(x: number, y: number, h = this.height(x, y)): [number, number] {
    return [this.ox + ((x - y) * TW) / 2, this.oy + ((x + y) * TH) / 2 - h * HS];
  }

  /** Центр верхней грани — сюда ставятся ноги. */
  cellCenter(x: number, y: number, h?: number): [number, number] {
    const [sx, sy] = this.cellTop(x, y, h);
    return [sx, sy + TH / 2];
  }

  /** Клетка под точкой холста: проверяем ромбы спереди назад, с учётом высоты. */
  pick(lx: number, ly: number): Cell | null {
    const { width: w, height: h } = this.arena;
    for (let d = w + h - 2; d >= 0; d--) {
      for (let x = Math.min(w - 1, d); x >= 0 && d - x < h; x--) {
        const y = d - x;
        const [sx, sy] = this.cellTop(x, y);
        const dx = Math.abs(lx - sx) / (TW / 2);
        const dy = Math.abs(ly - (sy + TH / 2)) / (TH / 2);
        if (dx + dy <= 1) return [x, y];
      }
    }
    return null;
  }

  private diamond(sx: number, sy: number): void {
    const c = this.ctx;
    c.beginPath();
    c.moveTo(sx, sy);
    c.lineTo(sx + TW / 2, sy + TH / 2);
    c.lineTo(sx, sy + TH);
    c.lineTo(sx - TW / 2, sy + TH / 2);
    c.closePath();
  }

  private drawCell(x: number, y: number, highlight: Highlight | undefined): void {
    const c = this.ctx;
    const h = this.heights[y][x];
    const [sx, sy] = this.cellTop(x, y);
    const depth = h * HS + BASE;
    // боковые грани: левая и правая
    c.fillStyle = this.left;
    c.beginPath();
    c.moveTo(sx - TW / 2, sy + TH / 2);
    c.lineTo(sx, sy + TH);
    c.lineTo(sx, sy + TH + depth);
    c.lineTo(sx - TW / 2, sy + TH / 2 + depth);
    c.closePath();
    c.fill();
    c.fillStyle = this.right;
    c.beginPath();
    c.moveTo(sx + TW / 2, sy + TH / 2);
    c.lineTo(sx, sy + TH);
    c.lineTo(sx, sy + TH + depth);
    c.lineTo(sx + TW / 2, sy + TH / 2 + depth);
    c.closePath();
    c.fill();
    // верх: тайл тайлсета, натянутый на ромб
    if (this.top) {
      c.save();
      this.diamond(sx, sy);
      c.clip();
      c.setTransform(TW / 32, TH / 32, -TW / 32, TH / 32, sx, sy);
      c.drawImage(this.top, 0, 0, 16, 16);
      c.restore();
    } else {
      c.fillStyle = "#5a5068";
      this.diamond(sx, sy);
      c.fill();
    }
    c.strokeStyle = "rgba(0, 0, 0, 0.22)";
    c.lineWidth = 1;
    this.diamond(sx, sy + 0.5);
    c.stroke();
    if (highlight) {
      const [fill, edge] = HIGHLIGHT[highlight];
      c.fillStyle = fill;
      this.diamond(sx, sy);
      c.fill();
      c.strokeStyle = edge;
      this.diamond(sx, sy + 0.5);
      c.stroke();
    }
  }

  private drawUnit(u: IsoUnit, now: number): void {
    const c = this.ctx;
    let { x, y } = u;
    if (u.lunge && now - u.lungeAt < 220) {
      const k = Math.sin(((now - u.lungeAt) / 220) * Math.PI) * 0.28;
      x += (u.lunge[0] - x) * k;
      y += (u.lunge[1] - y) * k;
    }
    const [cx, cy] = this.cellCenter(x, y, this.lerpHeight(u.x, u.y));
    // кольцо стороны и стрелка взгляда — от неё зависят фланг и спина
    const color = u.side === "party" ? "rgba(110, 190, 255, 0.95)" : "rgba(255, 105, 85, 0.95)";
    c.strokeStyle = color;
    c.lineWidth = 1;
    c.beginPath();
    c.ellipse(cx, cy, 9, 4.5, 0, 0, Math.PI * 2);
    c.stroke();
    const fx = ((u.facing[0] - u.facing[1]) * TW) / 2;
    const fy = ((u.facing[0] + u.facing[1]) * TH) / 2;
    const len = Math.hypot(fx, fy) || 1;
    const nx = fx / len, ny = fy / len;
    c.fillStyle = color;
    c.beginPath();
    c.moveTo(cx + nx * 13, cy + ny * 6.5);
    c.lineTo(cx + nx * 8 - ny * 3, cy + ny * 4 + nx * 1.5);
    c.lineTo(cx + nx * 8 + ny * 3, cy + ny * 4 - nx * 1.5);
    c.closePath();
    c.fill();

    const img = u.frames[Math.floor(now / 500) % u.frames.length];
    let px = Math.round(cx - (u.flip ? img.width - u.anchor[0] : u.anchor[0]));
    const py = Math.round(cy + 1 - u.anchor[1]);
    const hit = now - u.hitAt < 300;
    if (hit) px += Math.round(Math.sin(now / 25) * 2);
    c.save();
    if (hit) c.filter = "brightness(2.2)";
    if (u.flip) {
      c.scale(-1, 1);
      c.drawImage(img, -px - img.width, py);
    } else c.drawImage(img, px, py);
    c.restore();
    // полоска здоровья над головой
    const bw = 16;
    const top = py + this.spriteTop(img) - 4;
    c.fillStyle = "rgba(0, 0, 0, 0.75)";
    c.fillRect(Math.round(cx - bw / 2) - 1, top - 1, bw + 2, 4);
    c.fillStyle = u.side === "party" ? "#5ad05a" : "#e0503a";
    c.fillRect(Math.round(cx - bw / 2), top, Math.max(0, Math.round((bw * u.hp) / u.maxHp)), 2);
  }

  private spriteTops = new WeakMap<HTMLCanvasElement, number>();

  /** Первая непрозрачная строка спрайта — чтобы полоска HP висела над головой, а не над пустым полем кадра. */
  private spriteTop(img: HTMLCanvasElement): number {
    const hit = this.spriteTops.get(img);
    if (hit !== undefined) return hit;
    const data = pixels(img);
    let top = 0;
    search: for (let y = 0; y < img.height; y++) {
      for (let x = 0; x < img.width; x++) if (data[(y * img.width + x) * 4 + 3] > 0) { top = y; break search; }
    }
    this.spriteTops.set(img, top);
    return top;
  }

  private lerpHeight(x: number, y: number): number {
    const x0 = Math.floor(x), y0 = Math.floor(y);
    const fx = x - x0, fy = y - y0;
    const h0 = this.height(x0, y0);
    const h1 = this.height(fx > 0 ? x0 + 1 : x0, fy > 0 ? y0 + 1 : y0);
    return h0 + (h1 - h0) * Math.max(fx, fy);
  }

  draw(units: IsoUnit[], highlights: Map<string, Highlight>, now: number): void {
    const c = this.ctx;
    const { width: w, height: h } = this.arena;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const living = units.filter((u) => u.alive);
    for (let d = 0; d <= w + h - 2; d++) {
      for (let x = Math.max(0, d - h + 1); x <= Math.min(w - 1, d); x++) {
        const y = d - x;
        this.drawCell(x, y, highlights.get(`${x},${y}`));
      }
      // предметы и бойцы этой «диагонали» рисуем после её клеток, чтобы ближние перекрывали дальних
      for (let x = Math.max(0, d - h + 1); x <= Math.min(w - 1, d); x++) {
        const y = d - x;
        const prop = this.props.get(`${x},${y}`);
        if (prop) {
          const [cx, cy] = this.cellCenter(x, y, 0);
          c.drawImage(prop.canvas, Math.round(cx - prop.anchor[0]), Math.round(cy + 2 - prop.anchor[1]));
        }
      }
      for (const u of living) if (Math.ceil(u.x + u.y - 1e-6) === d) this.drawUnit(u, now);
    }
  }
}
