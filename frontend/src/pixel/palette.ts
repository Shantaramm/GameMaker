// Цвета: слоты палитры → RGB. Логика совпадает с pixelart/tools/preview.py.

import type { CreatureSpec, PortraitSpec } from "../types/game";
import { library } from "./library";

export type RGB = [number, number, number];
export type ColorMap = Map<string, RGB>;

const WHITE: RGB = [255, 255, 255];
const LIPS: RGB = [168, 68, 60];
const SHADE = 0.75; // S = s × 0.75 по светлоте в HSL (SPEC §5.7.1)

export function hexToRgb(hex: string): RGB {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;
}

export function mix(a: RGB, b: RGB, t: number): RGB {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)) as RGB;
}

function rgbToHsl([r, g, b]: RGB): [number, number, number] {
  const [rr, gg, bb] = [r / 255, g / 255, b / 255];
  const max = Math.max(rr, gg, bb);
  const min = Math.min(rr, gg, bb);
  const l = (max + min) / 2;
  if (max === min) return [0, l, 0];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === rr) h = (gg - bb) / d + (gg < bb ? 6 : 0);
  else if (max === gg) h = (bb - rr) / d + 2;
  else h = (rr - gg) / d + 4;
  return [h / 6, l, s];
}

function hslToRgb([h, l, s]: [number, number, number]): RGB {
  if (s === 0) return [l, l, l].map((v) => Math.round(v * 255)) as RGB;
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hue = (t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [hue(h + 1 / 3), hue(h), hue(h - 1 / 3)].map((v) => Math.round(v * 255)) as RGB;
}

export function shade(rgb: RGB, k = SHADE): RGB {
  const [h, l, s] = rgbToHsl(rgb);
  return hslToRgb([h, l * k, s]);
}

/** Цвет символа: явный слот, иначе верхний регистр = тень нижнего. */
export function resolve(ch: string, colors: ColorMap): RGB {
  const direct = colors.get(ch);
  if (direct) return direct;
  const base = colors.get(ch.toLowerCase());
  if (!base) throw new Error(`palette: нет цвета для слота '${ch}'`);
  const shaded = shade(base);
  colors.set(ch, shaded);
  return shaded;
}

function named(group: Record<string, string>, name: string, kind: string): RGB {
  const hex = group[name] ?? Object.values(group)[0];
  if (!(name in group)) console.warn(`pixelart: неизвестный цвет ${kind}:${name}`);
  return hexToRgb(hex);
}

function fixed(): ColorMap {
  return new Map(Object.entries(library.palettes.fixed).map(([k, v]) => [k, hexToRgb(v)]));
}

export function portraitColors(spec: PortraitSpec): ColorMap {
  const p = library.palettes;
  const colors = fixed();
  const skin = named(p.skin_tones, spec.skin, "skin");
  colors.set("s", skin);
  colors.set("h", named(p.hair_colors, spec.hair_color, "hair_color"));
  colors.set("e", named(p.eye_colors, spec.eye_color, "eye_color"));
  colors.set("c", named(p.cloth_colors, spec.outfit_color, "outfit_color"));
  colors.set("a", named(p.cloth_colors, spec.accent_color, "accent_color"));
  colors.set("r", mix(skin, LIPS, 0.45));
  return colors;
}

export function creatureColors(spec: CreatureSpec): ColorMap {
  const p = library.palettes;
  const colors = fixed();
  const accent = named(p.cloth_colors, spec.accent_color, "accent_color");
  colors.set("c", named(p.cloth_colors, spec.color, "color"));
  colors.set("a", accent);
  colors.set("e", mix(accent, WHITE, 0.45));
  return colors;
}

export function iconColors(tier: number): ColorMap {
  const p = library.palettes;
  const colors = fixed();
  for (const [k, v] of Object.entries(p.icon_fixed)) colors.set(k, hexToRgb(v));
  colors.set("c", hexToRgb(p.icon_tiers[String(tier)] ?? p.icon_tiers["1"]));
  return colors;
}

export function clothColor(name: string): RGB {
  return named(library.palettes.cloth_colors, name, "cloth");
}

// --- фоны ---

type Time = "day" | "dusk" | "night";
const TIME_TINT: Record<Time, [RGB, number, number] | null> = {
  day: null,
  dusk: [[224, 112, 64], 0.25, 0.85],
  night: [[24, 32, 74], 0.35, 0.55],
};
const UNTINTED = new Set(["l", "w", "n", "N"]);

export function tint(rgb: RGB, time: Time): RGB {
  const t = TIME_TINT[time];
  if (!t) return rgb;
  return shade(mix(rgb, t[0], t[1]), t[2]);
}

export interface SceneColors {
  colors: ColorMap;
  skyTop: RGB;
  skyBottom: RGB;
}

export function sceneColors(moodName: string, time: Time): SceneColors {
  const moods = library.palettes.mood_palettes;
  const mood = moods[moodName] ?? Object.values(moods)[0];
  if (!(moodName in moods)) console.warn(`pixelart: неизвестная палитра mood:${moodName}`);
  const [skyTop, skyBottom] = mood.sky[time].map(hexToRgb) as [RGB, RGB];
  const base = fixed();
  for (const [k, v] of Object.entries(mood.colors)) base.set(k, hexToRgb(v));
  const colors: ColorMap = new Map();
  for (const ch of "ofFgGpPqQvVaAkmM") colors.set(ch, tint(resolve(ch, base), time));
  colors.set("l", base.get("l")!);
  colors.set("w", base.get("w")!);
  colors.set("n", mix(skyBottom, WHITE, 0.45));
  colors.set("N", shade(mix(skyTop, skyBottom, 0.5), 0.8));
  for (const ch of UNTINTED) if (!colors.has(ch)) colors.set(ch, resolve(ch, base));
  return { colors, skyTop, skyBottom };
}
