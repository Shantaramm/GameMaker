// Тайлсеты и иконки (SPEC §5.8.5–5.8.6).

import type { BackgroundSpec } from "../types/game";
import { part, type Sprite } from "./library";
import { iconColors, sceneColors } from "./palette";
import { Raster } from "./sprite";

type Time = BackgroundSpec["time"];

const tileCache = new Map<string, HTMLCanvasElement>();

/** Тайл или декорация тайлсета, окрашенные настроенческой палитрой и временем суток. */
export function tileCanvas(tileset: string, name: string, mood: string, time: Time, decor = false): HTMLCanvasElement | null {
  const key = `${tileset}:${name}:${mood}:${time}:${decor}`;
  const hit = tileCache.get(key);
  if (hit) return hit;
  const ts = part("tileset", tileset);
  const sprite: Sprite | undefined = decor ? ts.decor?.[name] : ts.tiles?.[name];
  if (!sprite) return null;
  const raster = new Raster(sprite.w, sprite.h);
  raster.blit(sprite, [sprite.anchor[0], sprite.anchor[1]], sceneColors(mood, time).colors);
  const canvas = raster.toCanvas();
  tileCache.set(key, canvas);
  return canvas;
}

const iconCache = new Map<string, HTMLCanvasElement>();

export function iconCanvas(icon: string, tier: number): HTMLCanvasElement {
  const key = `${icon}:${tier}`;
  let canvas = iconCache.get(key);
  if (!canvas) {
    const raster = new Raster(16, 16);
    raster.blit(part("icon", icon), [0, 0], iconColors(tier));
    iconCache.set(key, (canvas = raster.toCanvas()));
  }
  return canvas;
}

const propCache = new Map<string, { canvas: HTMLCanvasElement; anchor: [number, number] }>();

/** Предмет фона (prop) как внешний вид сундука или исследуемого предмета на карте. anchor — точка основания. */
export function propCanvas(id: string, mood: string, time: Time): { canvas: HTMLCanvasElement; anchor: [number, number] } {
  const key = `${id}:${mood}:${time}`;
  let hit = propCache.get(key);
  if (!hit) {
    const sprite = part("prop", id);
    const raster = new Raster(sprite.w, sprite.h);
    raster.blit(sprite, sprite.anchor, sceneColors(mood, time).colors);
    hit = { canvas: raster.toCanvas(), anchor: sprite.anchor };
    propCache.set(key, hit);
  }
  return hit;
}
