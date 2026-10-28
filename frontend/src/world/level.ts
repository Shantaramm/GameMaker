// Рисование уровня (SPEC §5.6, §5.8): фон, тайлы, декорации, объекты.
// Геометрию строит бэкенд (levels.py) — здесь только картинка.

import { renderBackground, backgroundSeed } from "../pixel/background";
import { library, part } from "../pixel/library";
import { hash, pick, rng } from "../pixel/rng";
import { creatureMapFrames } from "../pixel/sprite";
import { propCanvas, tileCanvas } from "../pixel/tiles";
import { walkerFrames } from "../pixel/walker";
import type { Game, Level, Location } from "../types/game";

export const TILE = library.layout.tile;

type MapObject = NonNullable<Location["objects"]>[number];

export interface DecorPlacement {
  name: string;
  floor: number;
  x: number;
  wall: boolean;
}

/** Пиксельная координата пола под клеткой (floor, x): сюда встают ноги персонажа. */
export function feetY(level: Level, floor: number): number {
  return (level.floors[floor].y + 1) * TILE;
}

export function isIndoor(loc: Location): boolean {
  return part("tileset", loc.theme).setting === "indoor";
}

/** Декорации расставляются детерминированно (seed = hash(game_id + location_id)) и не мешают объектам и лестницам. */
export function planDecor(gameId: string, loc: Location, level: Level): DecorPlacement[] {
  const ts = part("tileset", loc.theme);
  const names = Object.entries(ts.decor ?? {}).filter(([, d]) => !d.wall || ts.tiles?.wall).map(([n]) => n);
  if (!names.length) return [];
  const random = rng(hash(`${gameId}:${loc.id}:decor`));
  const out: DecorPlacement[] = [];
  level.floors.forEach((f, floor) => {
    const busy = new Set<number>();
    const block = (x: number, r: number) => { for (let d = -r; d <= r; d++) busy.add(x + d); };
    for (const o of level.objects) if (o.floor === floor) block(o.x, 1);
    for (const l of level.links) {
      for (const [f2, x2] of [l.a, l.b] as unknown as [number, number][]) if (f2 === floor) block(x2, 1);
    }
    block(f.x0, 1);
    block(f.x1, 1);
    for (let x = f.x0 + 1; x < f.x1; x++) {
      if (busy.has(x) || random() > 0.28) continue;
      const name = pick(random, names);
      out.push({ name, floor, x, wall: ts.decor![name].wall });
      block(x, 1);
    }
  });
  return out;
}

/** Фон уровня: у улицы — небо и дальний план из 2а, растянутые по высоте и повторённые по ширине. */
export function drawBackdrop(ctx: CanvasRenderingContext2D, gameId: string, loc: Location, width: number, height: number, offsetX = 0): void {
  const bg = renderBackground({ ...loc.background, props: [] }, backgroundSeed(gameId, loc.id)).toCanvas();
  const scale = Math.max(1, Math.ceil(height / bg.height));
  const w = bg.width * scale;
  const top = height - bg.height * scale;
  for (let x = -((offsetX % w) + w) % w; x < width; x += w) ctx.drawImage(bg, x, top, w, bg.height * scale);
}

export function drawTerrain(ctx: CanvasRenderingContext2D, gameId: string, loc: Location, level: Level): void {
  const { mood_palette: mood, time } = loc.background;
  const tile = (name: string) => tileCanvas(loc.theme, name, mood, time);
  const indoor = isIndoor(loc);
  const groundRow = level.floors[0].y + 1;
  level.tiles.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      const at = (name: string) => {
        const c = tile(name);
        if (c) ctx.drawImage(c, x * TILE, y * TILE);
      };
      if (indoor && ch !== "#") at("wall");
      if (ch === "#") at(y === groundRow ? "floor" : "fill");
      else if (ch === "=") at("slab");
      else if (ch === "H") at("ladder");
      else if (ch === "|") at("edge");
    });
  });
  for (const d of planDecor(gameId, loc, level)) {
    const c = tileCanvas(loc.theme, d.name, mood, time, true);
    if (!c) continue;
    const bottom = feetY(level, d.floor) - (d.wall ? TILE * 1.5 : 0);
    ctx.drawImage(c, d.x * TILE, bottom - c.height);
  }
}

export interface ObjectArt {
  frames: HTMLCanvasElement[];
  /** точка кадра, которая ставится на (центр клетки, пол) */
  anchor: [number, number];
  flip?: boolean;
}

/** Как выглядит объект на карте. */
export function objectArt(game: Game, loc: Location, level: Level, obj: MapObject, opened = false): ObjectArt[] {
  const { mood_palette: mood, time } = loc.background;
  const placed = level.objects.find((o) => o.id === obj.id);
  const walker = library.layout.walker;
  const faceCenter = placed ? placed.x > level.width / 2 : false;
  switch (obj.type) {
    case "npc": {
      const c = [game.hero, ...(game.characters ?? [])].find((ch) => ch.id === obj.character);
      if (!c) return [];
      return [{ frames: walkerFrames(c.appearance, c.id).idle, anchor: walker.ref, flip: faceCenter }];
    }
    case "enemy":
      return obj.enemies.map((id) => {
        const e = (game.enemies ?? []).find((en) => en.id === id)!;
        if ("body" in e.appearance) return { frames: creatureMapFrames(e.appearance, e.id), anchor: [16, 31] as [number, number], flip: true };
        return { frames: walkerFrames(e.appearance, e.id).idle, anchor: walker.ref, flip: true };
      });
    case "chest":
    case "thing":
    case "gather":
    case "station": {
      const p = propCanvas(obj.look, mood, time);
      return [{ frames: [p.canvas], anchor: p.anchor }];
    }
    case "exit": {
      if (obj.kind !== "door") return [];
      const name = obj.requires && !opened ? "door_locked" : "door";
      const c = tileCanvas(loc.theme, name, mood, time);
      return c ? [{ frames: [c], anchor: [TILE / 2, c.height] }] : [];
    }
  }
}

export function drawArt(ctx: CanvasRenderingContext2D, art: ObjectArt, px: number, py: number, frame = 0): void {
  const img = art.frames[frame % art.frames.length];
  const x = Math.round(px - (art.flip ? img.width - art.anchor[0] : art.anchor[0]));
  const y = Math.round(py - art.anchor[1]);
  if (art.flip) {
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(img, -x - img.width, y);
    ctx.restore();
  } else ctx.drawImage(img, x, y);
}

/** Стрелка у выхода за край уровня. */
export function drawEdgeMarker(ctx: CanvasRenderingContext2D, level: Level, floor: number, x: number, left: boolean): void {
  const y = feetY(level, floor) - TILE;
  const cx = x * TILE + TILE / 2;
  ctx.fillStyle = "rgba(255,255,255,0.8)";
  for (let i = 0; i < 2; i++) {
    const dx = (left ? -1 : 1) * (i * 4);
    ctx.beginPath();
    ctx.moveTo(cx + dx + (left ? 3 : -3), y - 4);
    ctx.lineTo(cx + dx + (left ? -1 : 1), y);
    ctx.lineTo(cx + dx + (left ? 3 : -3), y + 4);
    ctx.fill();
  }
}

/** Весь уровень одной картинкой: для /lab и как первый кадр в игре. */
export function renderLevel(game: Game, gameId: string, locationId: string, frame = 0): HTMLCanvasElement {
  const loc = game.locations.find((l) => l.id === locationId)!;
  const level = game.levels![locationId];
  const canvas = document.createElement("canvas");
  canvas.width = level.width * TILE;
  canvas.height = level.height * TILE;
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingEnabled = false;
  if (!isIndoor(loc)) drawBackdrop(ctx, gameId, loc, canvas.width, canvas.height);
  drawTerrain(ctx, gameId, loc, level);
  for (const obj of loc.objects ?? []) {
    const placed = level.objects.find((o) => o.id === obj.id);
    if (!placed) continue;
    const px = placed.x * TILE + TILE / 2;
    const py = feetY(level, placed.floor);
    if (obj.type === "exit" && obj.kind !== "door") drawEdgeMarker(ctx, level, placed.floor, placed.x, obj.kind === "left_edge");
    objectArt(game, loc, level, obj).forEach((art, i, all) => drawArt(ctx, art, px + (i - (all.length - 1) / 2) * 14, py, frame));
  }
  const spawn = level.spawns.find((s) => s.from === "default")!;
  drawArt(ctx, { frames: walkerFrames(game.hero.appearance, game.hero.id).idle, anchor: library.layout.walker.ref },
    spawn.x * TILE + TILE / 2, feetY(level, spawn.floor), frame);
  return canvas;
}
