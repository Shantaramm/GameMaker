// Спрайт персонажа в полный рост для карты (SPEC §5.8.3). Выводится из той же PortraitSpec, что и портрет.

import type { PortraitSpec } from "../types/game";
import { has, library, part, type Sprite } from "./library";
import { portraitColors } from "./palette";
import { Raster } from "./sprite";

export type Anim = "idle" | "walk" | "climb";
export const ANIMS: Anim[] = ["idle", "walk", "climb"];

/** Слои снизу вверх: hair.back → outfit → head → facial_hair → hair → accessory. Смотрит вправо. */
export function renderWalker(spec: PortraitSpec, anim: Anim, frame: number): Raster {
  const { w, h, ref } = library.layout.walker;
  const raster = new Raster(w, h);
  const colors = portraitColors(spec);
  const pick = (sprites: Record<string, Sprite[]> | undefined) => sprites?.[anim]?.[frame];
  const draw = (sprite: Sprite | undefined) => sprite && raster.blit(sprite, ref, colors);

  const hair = spec.hair === "none" ? null : part("walker_hair", spec.hair);
  draw(pick(hair?.back_frames));
  draw(pick(part("walker_outfit", spec.outfit).frames));
  draw(pick(part("walker_head", spec.head).frames));
  if (spec.facial_hair && has("walker_facial_hair", spec.facial_hair)) draw(pick(part("walker_facial_hair", spec.facial_hair).frames));
  draw(pick(hair?.frames));
  // Аксессуары без пары в 16×32 (шрам, веснушки, серьги…) на карте не видны — это нормально.
  for (const id of spec.accessory ?? []) if (has("walker_accessory", id)) draw(pick(part("walker_accessory", id).frames));
  return raster;
}

export type WalkerFrames = Record<Anim, HTMLCanvasElement[]>;

const cache = new Map<string, WalkerFrames>();

export function walkerFrames(spec: PortraitSpec, key = JSON.stringify(spec)): WalkerFrames {
  let frames = cache.get(key);
  if (!frames) {
    frames = {} as WalkerFrames;
    for (const anim of ANIMS) {
      frames[anim] = Array.from({ length: library.layout.walker.frames[anim] }, (_, i) => renderWalker(spec, anim, i).toCanvas());
    }
    cache.set(key, frames);
  }
  return frames;
}

/** Кадры в секунду для анимаций. */
export const FPS: Record<Anim, number> = { idle: 2, walk: 8, climb: 6 };
