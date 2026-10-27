// Случайные спецификации для PixelLab и скриншотов.

import type { BackgroundSpec, CreatureSpec, PortraitSpec } from "../types/game";
import { ids, library } from "./library";
import { pick, rng } from "./rng";

const names = (group: Record<string, unknown>) => Object.keys(group);

export function randomPortrait(seed: number): PortraitSpec {
  const r = rng(seed);
  const p = library.palettes;
  const accessories = ids("accessory");
  const count = pick(r, [0, 0, 1, 1, 2]);
  const accessory: string[] = [];
  while (accessory.length < count) {
    const a = pick(r, accessories);
    if (!accessory.includes(a)) accessory.push(a);
  }
  const spec: PortraitSpec = {
    head: pick(r, ids("head")),
    skin: pick(r, names(p.skin_tones)),
    hair: r() < 0.08 ? "none" : pick(r, ids("hair")),
    hair_color: pick(r, names(p.hair_colors)),
    eyes: pick(r, ids("eyes")),
    eye_color: pick(r, names(p.eye_colors)),
    brows: pick(r, ids("brows")),
    mouth: pick(r, ids("mouth")),
    outfit: pick(r, ids("outfit")),
    outfit_color: pick(r, names(p.cloth_colors)),
    accent_color: pick(r, names(p.cloth_colors)),
    accessory,
    bg_color: pick(r, names(p.cloth_colors)),
  };
  if (r() < 0.3) spec.facial_hair = pick(r, ids("facial_hair"));
  return spec;
}

export function randomCreature(seed: number): CreatureSpec {
  const r = rng(seed);
  const cloth = names(library.palettes.cloth_colors);
  const features = ids("creature_feature").filter(() => r() < 0.2).slice(0, 3);
  return {
    body: pick(r, ids("creature_body")),
    color: pick(r, cloth),
    accent_color: pick(r, cloth),
    features,
    size: pick(r, ["small", "medium", "large"] as const),
  };
}

export function randomBackground(seed: number): BackgroundSpec {
  const r = rng(seed);
  const far = pick(r, ids("far"));
  const setting = library.slots.far.get(far)!.setting === "indoor" ? "indoor" : "outdoor";
  const fitting = ids("prop").filter((id) => {
    const s = library.slots.prop.get(id)!.setting;
    return s === "any" || s === setting;
  });
  const count = 2 + Math.floor(r() * 4);
  const props = Array.from({ length: count }, (_, i) => ({
    id: pick(r, fitting),
    x: Math.round(((i + 0.5) / count) * 160 + (r() - 0.5) * 14),
  }));
  const grounds = setting === "indoor" ? ["planks", "rock", "metal", "cobblestone"] : ids("ground");
  return {
    setting,
    time: pick(r, ["day", "dusk", "night"] as const),
    ...(setting === "outdoor" ? { sky: pick(r, ids("sky")) } : {}),
    far,
    props,
    ground: pick(r, grounds),
    overlay: pick(r, ["none", "none", "rain", "fog", "snow", "dust"] as const),
    mood_palette: pick(r, Object.keys(library.palettes.mood_palettes)),
  };
}
