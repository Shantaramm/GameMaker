// Сборка портретов (48×48) и существ (64×64) из деталей библиотеки.

import type { CreatureSpec, PortraitSpec } from "../types/game";
import { library, part, type Sprite } from "./library";
import { clothColor, creatureColors, portraitColors, resolve, type ColorMap, type RGB } from "./palette";

export type Emotion = "neutral" | "angry" | "sad" | "happy" | "scared" | "surprised";

/** Пиксельный буфер с прозрачностью. */
export class Raster {
  readonly data: Uint8ClampedArray<ArrayBuffer>;

  constructor(readonly w: number, readonly h: number) {
    this.data = new Uint8ClampedArray(new ArrayBuffer(w * h * 4));
  }

  fill(rgb: RGB): void {
    for (let i = 0; i < this.w * this.h; i++) this.put(i, rgb);
  }

  put(index: number, [r, g, b]: RGB, alpha = 255): void {
    const o = index * 4;
    if (alpha >= 255) {
      this.data[o] = r;
      this.data[o + 1] = g;
      this.data[o + 2] = b;
      this.data[o + 3] = 255;
      return;
    }
    const a = alpha / 255;
    const under = this.data[o + 3] / 255;
    const out = a + under * (1 - a);
    for (let c = 0; c < 3; c++) {
      const v = [r, g, b][c];
      this.data[o + c] = out ? (v * a + this.data[o + c] * under * (1 - a)) / out : 0;
    }
    this.data[o + 3] = out * 255;
  }

  set(x: number, y: number, rgb: RGB, alpha = 255): void {
    if (x >= 0 && y >= 0 && x < this.w && y < this.h) this.put(y * this.w + x, rgb, alpha);
  }

  /**
   * Рисует спрайт так, что его anchor попадает в точку at.
   * mask — рисовать только в этих пикселях; record — сюда пишутся пиксели кожи (s/S).
   */
  blit(sprite: Sprite, at: [number, number], colors: ColorMap, mask?: Set<number>, record?: Set<number>): void {
    const ox = at[0] - sprite.anchor[0];
    const oy = at[1] - sprite.anchor[1];
    sprite.pixels.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        const ch = row[x];
        if (ch === ".") continue;
        const px = ox + x;
        const py = oy + y;
        if (px < 0 || py < 0 || px >= this.w || py >= this.h) continue;
        const index = py * this.w + px;
        if (mask && !mask.has(index)) continue;
        this.put(index, resolve(ch, colors));
        if (record && (ch === "s" || ch === "S")) record.add(index);
      }
    });
  }

  toCanvas(): HTMLCanvasElement {
    const canvas = document.createElement("canvas");
    canvas.width = this.w;
    canvas.height = this.h;
    canvas.getContext("2d")!.putImageData(new ImageData(this.data, this.w, this.h), 0, 0);
    return canvas;
  }
}

function variant(slot: "eyes" | "brows" | "mouth", id: string, emotion: Emotion): Sprite {
  const p = part(slot, id);
  return p.variants?.[emotion] ?? p.variants?.neutral ?? p;
}

/** Слои снизу вверх (SPEC §5.7.2): back_hair → outfit → head → лицо → front_hair → accessory. */
export function renderPortrait(spec: PortraitSpec, emotion: Emotion = "neutral"): Raster {
  const { w, h, ref } = library.layout.portrait;
  const raster = new Raster(w, h);
  raster.fill(clothColor(spec.bg_color));
  const colors = portraitColors(spec);
  const hair = spec.hair === "none" ? null : part("hair", spec.hair);
  const skin = new Set<number>();

  if (hair?.back) raster.blit(hair.back, ref, colors);
  raster.blit(part("outfit", spec.outfit), ref, colors);
  raster.blit(part("head", spec.head), ref, colors, undefined, skin);
  raster.blit(variant("eyes", spec.eyes, emotion), ref, colors);
  raster.blit(variant("brows", spec.brows, emotion), ref, colors);
  if (spec.facial_hair) {
    const fh = part("facial_hair", spec.facial_hair);
    raster.blit(fh, ref, colors, fh.clip === "head" ? skin : undefined);
  }
  raster.blit(variant("mouth", spec.mouth, emotion), ref, colors);
  if (hair) raster.blit(hair, ref, colors);
  for (const id of spec.accessory ?? []) {
    const acc = part("accessory", id);
    raster.blit(acc, ref, colors, acc.clip === "head" ? skin : undefined);
  }
  return raster;
}

/** Тело в REF, особенности — anchor-ом в точку крепления тела; layer=back рисуется до тела. */
export function renderCreature(spec: CreatureSpec): Raster {
  const { w, h, ref } = library.layout.creature;
  const raster = new Raster(w, h);
  const colors = creatureColors(spec);
  const body = part("creature_body", spec.body);
  const origin: [number, number] = [ref[0] - body.anchor[0], ref[1] - body.anchor[1]];
  const features = (spec.features ?? []).map((id) => part("creature_feature", id));

  const place = (f: (typeof features)[number]) => {
    const point = body.points?.[f.attach ?? ""] ?? [body.anchor[0], 0];
    raster.blit(f, [origin[0] + point[0], origin[1] + point[1]], colors);
  };

  features.filter((f) => f.layer === "back").forEach(place);
  raster.blit(body, ref, colors);
  features.filter((f) => f.layer !== "back").forEach(place);
  return raster;
}

/** Уменьшение вдвое: в каждом блоке 2×2 побеждает самый частый цвет (при равенстве — более тёмный, это контур). */
export function downscale(src: Raster): Raster {
  const out = new Raster(src.w >> 1, src.h >> 1);
  for (let y = 0; y < out.h; y++)
    for (let x = 0; x < out.w; x++) {
      const counts = new Map<number, number>();
      for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
        const o = ((y * 2 + dy) * src.w + x * 2 + dx) * 4;
        if (src.data[o + 3] === 0) continue;
        const key = (src.data[o] << 16) | (src.data[o + 1] << 8) | src.data[o + 2];
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      const total = [...counts.values()].reduce((a, b) => a + b, 0);
      if (total < 2) continue;
      const luma = (k: number) => ((k >> 16) & 255) * 0.3 + ((k >> 8) & 255) * 0.59 + (k & 255) * 0.11;
      const best = [...counts.entries()].sort((a, b) => b[1] - a[1] || luma(a[0]) - luma(b[0]))[0][0];
      out.set(x, y, [(best >> 16) & 255, (best >> 8) & 255, best & 255]);
    }
  return out;
}

function mirrored(src: Raster): Raster {
  const out = new Raster(src.w, src.h);
  for (let y = 0; y < src.h; y++)
    for (let x = 0; x < src.w; x++) {
      const i = (y * src.w + x) * 4;
      const j = (y * src.w + (src.w - 1 - x)) * 4;
      out.data.set(src.data.subarray(i, i + 4), j);
    }
  return out;
}

/** «Вдох»: всё, кроме нижней строки, опускается на пиксель. */
function breathe(src: Raster): Raster {
  const out = new Raster(src.w, src.h);
  const row = src.w * 4;
  out.data.set(src.data.subarray(0, (src.h - 2) * row), row);
  out.data.set(src.data.subarray((src.h - 1) * row), (src.h - 1) * row);
  return out;
}

/**
 * Существо на карте (SPEC §5.8.4): боевой спрайт с особенностями, уменьшенный вдвое, мордой вправо.
 * Два кадра стойки. Отдельных деталей для карты нет — так существо на карте всегда совпадает с собой в бою.
 */
export function creatureMapFrames(spec: CreatureSpec, key = JSON.stringify(spec)): HTMLCanvasElement[] {
  const k = `m:${key}`;
  const hit = mapCache.get(k);
  if (hit) return hit;
  let small = downscale(renderCreature(spec));
  if (part("creature_body", spec.body).faces === "left") small = mirrored(small);
  const frames = [small.toCanvas(), breathe(small).toCanvas()];
  mapCache.set(k, frames);
  return frames;
}

const mapCache = new Map<string, HTMLCanvasElement[]>();

export const CREATURE_SCALE: Record<CreatureSpec["size"], number> = { small: 1, medium: 1.5, large: 2 };

// Кэш готовых картинок: портрет одинаков во всей игре (SPEC §5.2), считать его дважды незачем.
const cache = new Map<string, HTMLCanvasElement>();

export function portraitCanvas(spec: PortraitSpec, emotion: Emotion = "neutral", key = JSON.stringify(spec)): HTMLCanvasElement {
  const k = `p:${key}:${emotion}`;
  let canvas = cache.get(k);
  if (!canvas) cache.set(k, (canvas = renderPortrait(spec, emotion).toCanvas()));
  return canvas;
}

export function creatureCanvas(spec: CreatureSpec, key = JSON.stringify(spec)): HTMLCanvasElement {
  const k = `c:${key}`;
  let canvas = cache.get(k);
  if (!canvas) cache.set(k, (canvas = renderCreature(spec).toCanvas()));
  return canvas;
}

/** Копия холста для вставки в DOM с целочисленным масштабом и pixelated-рендером. */
export function scaled(source: HTMLCanvasElement, scale: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = source.width;
  canvas.height = source.height;
  canvas.getContext("2d")!.drawImage(source, 0, 0);
  canvas.className = "pixel";
  canvas.style.width = `${source.width * scale}px`;
  canvas.style.height = `${source.height * scale}px`;
  return canvas;
}

/** Наибольший целый масштаб, при котором картинка шириной w влезает в available (в пределах min…max). */
export function fitScale(w: number, available: number, min = 2, max = 8): number {
  return Math.max(min, Math.min(max, Math.floor(available / w)));
}
