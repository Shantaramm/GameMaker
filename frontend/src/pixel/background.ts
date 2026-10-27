// Фон сцены 160×90: статичные слои + анимированный overlay (SPEC §5.7.4).

import type { BackgroundSpec } from "../types/game";
import { library, part } from "./library";
import { mix, sceneColors, type RGB } from "./palette";
import { hash, rng } from "./rng";
import { Raster } from "./sprite";

const SKY_BANDS = 7;
const STAR_COLORS: RGB[] = [[230, 230, 240], [160, 160, 190]];

export function backgroundSeed(gameId: string, sceneId: string): number {
  return hash(gameId + sceneId);
}

/** Неподвижная часть фона: небо, звёзды, дальний план, земля, предметы — с тонированием по времени суток. */
export function renderBackground(spec: BackgroundSpec, seed: number): Raster {
  const { w, h, horizon, prop_base_y } = library.layout.background;
  const raster = new Raster(w, h);
  const { colors, skyTop, skyBottom } = sceneColors(spec.mood_palette, spec.time);

  // Градиент неба полосами, с шахматным дизерингом на границах полос.
  for (let y = 0; y < h; y++) {
    const pos = (Math.min(y, horizon) * SKY_BANDS) / horizon;
    const band = Math.min(SKY_BANDS - 1, Math.floor(pos));
    for (let x = 0; x < w; x++) {
      const step = pos % 1 > 0.8 && (x + y) % 2 === 0 && band < SKY_BANDS - 1 ? 1 : 0;
      raster.set(x, y, mix(skyTop, skyBottom, (band + step) / (SKY_BANDS - 1)));
    }
  }

  const random = rng(seed);
  if (spec.setting === "outdoor" && spec.sky) {
    const sky = part("sky", spec.sky);
    const stars = spec.time === "day" ? 0 : sky.stars ?? 0;
    for (let i = 0; i < stars; i++) {
      const x = Math.floor(random() * w);
      const y = Math.floor(random() * (horizon - 12));
      raster.set(x, y, random() < 0.7 ? STAR_COLORS[0] : STAR_COLORS[1]);
    }
    raster.blit(sky, [0, 0], colors);
  }
  raster.blit(part("far", spec.far), [0, 0], colors);
  raster.blit(part("ground", spec.ground), [0, 0], colors);
  for (const prop of spec.props ?? []) raster.blit(part("prop", prop.id), [prop.x, prop_base_y], colors);
  return raster;
}

// --- overlay -----------------------------------------------------------------

interface Particle {
  x: number;
  y: number;
  speed: number;
  size: number;
  phase: number;
}

type Overlay = NonNullable<BackgroundSpec["overlay"]>;

const OVERLAY_COUNT: Record<Overlay, number> = { rain: 70, snow: 50, dust: 24, fog: 5, none: 0 };

function spawn(kind: Overlay, random: () => number, w: number, h: number): Particle[] {
  return Array.from({ length: OVERLAY_COUNT[kind] }, () => ({
    x: random() * w,
    y: random() * h,
    speed: kind === "rain" ? 90 + random() * 40 : kind === "snow" ? 8 + random() * 10 : 2 + random() * 4,
    size: kind === "fog" ? 30 + random() * 40 : random() < 0.3 ? 2 : 1,
    phase: random() * Math.PI * 2,
  }));
}

/** Рисует кадр overlay поверх статичного фона. t — секунды. */
function drawOverlay(raster: Raster, kind: Overlay, particles: Particle[], t: number, light: RGB): void {
  const { w, h } = raster;
  for (const p of particles) {
    if (kind === "rain") {
      const y = (p.y + t * p.speed) % (h + 8);
      const x = (p.x - t * p.speed * 0.25 + w * 10) % w;
      for (let i = 0; i < 4; i++) raster.set(Math.floor(x + i * 0.25), Math.floor(y - i), light, 150);
    } else if (kind === "snow") {
      const y = (p.y + t * p.speed) % h;
      const x = (p.x + Math.sin(t + p.phase) * 3 + w) % w;
      raster.set(Math.floor(x), Math.floor(y), [240, 240, 248], 230);
      if (p.size > 1) raster.set(Math.floor(x) + 1, Math.floor(y), [240, 240, 248], 160);
    } else if (kind === "dust") {
      const x = (p.x + t * p.speed + w) % w;
      const y = (p.y + Math.sin(t * 0.7 + p.phase) * 4 + h) % h;
      raster.set(Math.floor(x), Math.floor(y), light, 110 + Math.floor(60 * Math.sin(t * 2 + p.phase)));
    } else if (kind === "fog") {
      // Клубы тумана: плотные в центре, редеющие к краям. Порог — детерминированный шум
      // по координатам, поэтому край «пиксельный» и не мерцает между кадрами.
      const cx = ((p.x + t * p.speed) % (w + p.size * 2)) - p.size;
      const cy = h * 0.5 + (p.y / h) * h * 0.45;
      const ry = 5 + p.size / 12;
      for (let y = Math.floor(cy - ry); y < cy + ry; y++)
        for (let x = Math.floor(cx - p.size); x < cx + p.size; x++) {
          const d = ((x - cx) / p.size) ** 2 + ((y - cy) / ry) ** 2;
          const noise = (((x * 73856093) ^ (y * 19349663)) >>> 0) % 97 / 97;
          if (d < 1 && noise > d * 0.9 + 0.1) raster.set(x, y, light, Math.round(90 * (1 - d)));
        }
    }
  }
}

/** Фон в DOM-холсте с анимацией overlay. Вызывающий отвечает за stop(). */
export class BackgroundView {
  readonly canvas: HTMLCanvasElement;
  private frame = 0;
  private readonly base: Raster;
  private readonly particles: Particle[];
  private readonly light: RGB;

  constructor(private readonly spec: BackgroundSpec, seed: number, animate = true) {
    this.base = renderBackground(spec, seed);
    const { w, h } = library.layout.background;
    this.canvas = document.createElement("canvas");
    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.className = "pixel";
    const kind = spec.overlay ?? "none";
    this.particles = spawn(kind, rng(seed ^ 0x9e3779b9), w, h);
    this.light = mix(sceneColors(spec.mood_palette, spec.time).skyBottom, [255, 255, 255], 0.6);
    this.draw(0);
    if (animate && kind !== "none") {
      const tick = (ms: number) => {
        this.draw(ms / 1000);
        this.frame = requestAnimationFrame(tick);
      };
      this.frame = requestAnimationFrame(tick);
    }
  }

  private draw(t: number): void {
    const frame = new Raster(this.base.w, this.base.h);
    frame.data.set(this.base.data);
    drawOverlay(frame, this.spec.overlay ?? "none", this.particles, t, this.light);
    this.canvas.getContext("2d")!.putImageData(new ImageData(frame.data, frame.w, frame.h), 0, 0);
  }

  stop(): void {
    cancelAnimationFrame(this.frame);
  }
}
