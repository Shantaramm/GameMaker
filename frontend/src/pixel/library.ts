// Библиотека деталей из /pixelart/library, собирается в бандл при сборке.

export interface Sprite {
  w: number;
  h: number;
  anchor: [number, number];
  pixels: string[];
}

export interface Part extends Sprite {
  id: string;
  slot: string;
  description: string;
  variants?: Record<string, Sprite>; // эмоции: глаза, брови, рот
  back?: Sprite; // задний слой причёски
  clip?: "head"; // рисовать только поверх кожи головы
  points?: Record<string, [number, number]>; // точки крепления тела существа
  attach?: string; // к какой точке крепится особенность
  layer?: "back" | "front";
  setting?: "indoor" | "outdoor" | "any";
  stars?: number; // процедурные звёзды неба
}

export interface MoodPalette {
  description: string;
  sky: Record<"day" | "dusk" | "night", [string, string]>;
  colors: Record<string, string>;
}

export interface Palettes {
  fixed: Record<string, string>;
  skin_tones: Record<string, string>;
  hair_colors: Record<string, string>;
  eye_colors: Record<string, string>;
  cloth_colors: Record<string, string>;
  mood_palettes: Record<string, MoodPalette>;
}

export interface Layout {
  portrait: { w: number; h: number; ref: [number, number]; emotions: string[] };
  creature: { w: number; h: number; ref: [number, number] };
  background: { w: number; h: number; horizon: number; prop_base_y: number };
}

export interface Library {
  palettes: Palettes;
  layout: Layout;
  slots: Record<string, Map<string, Part>>;
}

export type Slot =
  | "head" | "hair" | "eyes" | "brows" | "mouth" | "facial_hair" | "outfit" | "accessory"
  | "creature_body" | "creature_feature" | "sky" | "far" | "ground" | "prop";

const files = import.meta.glob("../../../pixelart/library/**/*.json", { eager: true, import: "default" });

function build(): Library {
  let palettes: Palettes | undefined;
  let layout: Layout | undefined;
  const slots: Record<string, Map<string, Part>> = {};
  for (const [path, data] of Object.entries(files)) {
    if (path.endsWith("/palettes.json")) palettes = data as Palettes;
    else if (path.endsWith("/layout.json")) layout = data as Layout;
    else
      for (const part of data as Part[]) {
        (slots[part.slot] ??= new Map()).set(part.id, part);
      }
  }
  if (!palettes || !layout) throw new Error("pixelart library: palettes.json или layout.json не найдены");
  return { palettes, layout, slots };
}

export const library: Library = build();

export function ids(slot: Slot): string[] {
  return [...(library.slots[slot]?.keys() ?? [])];
}

const warned = new Set<string>();

/** Деталь по id; неизвестный id заменяется первой деталью слота (SPEC §6.7), без падения. */
export function part(slot: Slot, id: string): Part {
  const parts = library.slots[slot];
  const found = parts?.get(id);
  if (found) return found;
  const fallback = parts?.values().next().value;
  if (!fallback) throw new Error(`pixelart library: пустой слот ${slot}`);
  const key = `${slot}:${id}`;
  if (!warned.has(key)) {
    warned.add(key);
    console.warn(`pixelart: неизвестная деталь ${key}, подставлена ${fallback.id}`);
  }
  return fallback;
}
