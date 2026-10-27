// Карта локации: камера, ходьба по тапу и клавишам, лестницы, касание врагов, выходы (SPEC §5.7).

import { findPath, type Cell } from "../engine/pathfinding";
import type { GameController } from "../engine/runtime";
import type { MapObject } from "../engine/world";
import { BackgroundView, backgroundSeed } from "../pixel/background";
import { library } from "../pixel/library";
import { walkerFrames, FPS, type Anim } from "../pixel/walker";
import { drawArt, drawEdgeMarker, drawTerrain, feetY, isIndoor, objectArt, TILE, type ObjectArt } from "./level";

const WALK_SPEED = 4.5;   // тайлов в секунду
const CLIMB_SPEED = 3.5;
const TILES_ACROSS = 12;  // сколько тайлов по ширине хочется видеть на телефоне

interface Mover {
  floor: number;
  x: number;        // тайлы, дробные во время движения
  y: number;        // пиксели: линия ног
  facing: 1 | -1;
  anim: Anim;
}

export class MapScene {
  readonly canvas = document.createElement("canvas");
  private ctx = this.canvas.getContext("2d")!;
  private terrain: HTMLCanvasElement | null = null;
  private backdrop: BackgroundView | null = null;
  private hero!: Mover;
  private buddy: Mover | null = null;
  private path: Cell[] = [];
  private target: MapObject | null = null;
  private keys = new Set<string>();
  private scale = 2;
  private cam = { x: 0, y: 0 };
  private frame = 0;
  private last = 0;
  private stopped = false;
  paused = false; // открыта панель (инвентарь, журнал…)

  constructor(private readonly host: HTMLElement, private readonly game: GameController) {
    this.canvas.className = "map";
    host.append(this.canvas);
    new ResizeObserver(() => this.resize()).observe(host);
    this.canvas.addEventListener("pointerdown", (e) => this.tap(e));
    window.addEventListener("keydown", this.onKey);
    window.addEventListener("keyup", this.onKeyUp);
    this.resize();
    requestAnimationFrame(this.loop);
  }

  destroy(): void {
    this.stopped = true;
    this.backdrop?.stop();
    window.removeEventListener("keydown", this.onKey);
    window.removeEventListener("keyup", this.onKeyUp);
  }

  /** Вызывается контроллером при входе в локацию. */
  enterLocation(): void {
    const loc = this.game.location;
    const level = this.game.level;
    this.backdrop?.stop();
    this.backdrop = isIndoor(loc) ? null : new BackgroundView({ ...loc.background, props: [] }, backgroundSeed(this.game.gameId, loc.id));
    this.terrain = document.createElement("canvas");
    this.terrain.width = level.width * TILE;
    this.terrain.height = level.height * TILE;
    drawTerrain(this.terrain.getContext("2d")!, this.game.gameId, loc, level);
    const s = this.game.state;
    this.hero = { floor: s.floor, x: s.x, y: feetY(level, s.floor), facing: 1, anim: "idle" };
    this.buddy = null;
    this.path = [];
    this.target = null;
    this.resize();
    this.centerCamera(true);
  }

  // --- размеры и камера ---

  private resize(): void {
    const w = this.host.clientWidth || 360;
    const h = this.host.clientHeight || 640;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    const levelH = this.terrain?.height ?? 128;
    const byWidth = Math.floor(w / (TILE * TILES_ACROSS));
    const byHeight = Math.floor(h / levelH);
    this.scale = Math.max(2, Math.min(Math.max(byWidth, 2), Math.max(byHeight, 2), 4));
  }

  private get view() {
    const dpr = window.devicePixelRatio || 1;
    return { w: this.canvas.width / dpr / this.scale, h: this.canvas.height / dpr / this.scale };
  }

  private centerCamera(snap = false): void {
    if (!this.terrain) return;
    const { w, h } = this.view;
    const W = this.terrain.width;
    const H = this.terrain.height;
    const tx = W <= w ? (W - w) / 2 : Math.min(Math.max(this.hero.x * TILE + TILE / 2 - w / 2, 0), W - w);
    const ty = H <= h ? H - h : Math.min(Math.max(this.hero.y - TILE * 3 - h / 2, 0), H - h);
    const k = snap ? 1 : 0.15;
    this.cam.x += (tx - this.cam.x) * k;
    this.cam.y += (ty - this.cam.y) * k;
  }

  // --- ввод ---

  private toWorld(clientX: number, clientY: number): [number, number] {
    const r = this.canvas.getBoundingClientRect();
    return [(clientX - r.left) / this.scale + this.cam.x, (clientY - r.top) / this.scale + this.cam.y];
  }

  /** Экранные координаты центра объекта (для подсказок и сквозного теста). */
  screenPos(objectId: string): { x: number; y: number } | null {
    const placed = this.game.level.objects.find((o) => o.id === objectId);
    if (!placed) return null;
    const r = this.canvas.getBoundingClientRect();
    const wx = placed.x * TILE + TILE / 2;
    const wy = feetY(this.game.level, placed.floor) - TILE / 2;
    return { x: r.left + (wx - this.cam.x) * this.scale, y: r.top + (wy - this.cam.y) * this.scale };
  }

  private tap(e: PointerEvent): void {
    if (this.blocked) return;
    const [wx, wy] = this.toWorld(e.clientX, e.clientY);
    const hit = this.hitObject(wx, wy);
    const level = this.game.level;
    if (hit) {
      const placed = level.objects.find((o) => o.id === hit.id)!;
      this.walkTo([placed.floor, placed.x], hit);
      return;
    }
    // ближайший этаж по вертикали, клетка по горизонтали
    let floor = 0;
    let best = Infinity;
    level.floors.forEach((_f, i) => {
      const d = Math.abs(feetY(level, i) - TILE - wy);
      if (d < best) [best, floor] = [d, i];
    });
    const f = level.floors[floor];
    const x = Math.min(f.x1, Math.max(f.x0, Math.floor(wx / TILE)));
    this.walkTo([floor, x], this.edgeExitAt(floor, x));
  }

  private hitObject(wx: number, wy: number): MapObject | null {
    const level = this.game.level;
    for (const obj of this.game.location.objects ?? []) {
      if (!this.game.present(obj)) continue;
      const placed = level.objects.find((o) => o.id === obj.id);
      if (!placed) continue;
      const cx = placed.x * TILE + TILE / 2;
      const bottom = feetY(level, placed.floor);
      const arts = objectArt(this.game.world.game, this.game.location, level, obj);
      const height = Math.max(TILE * 2, ...arts.map((a) => a.anchor[1]));
      const half = Math.max(TILE * 0.8, ...arts.map((a) => a.frames[0].width / 2));
      if (Math.abs(wx - cx) <= half && wy <= bottom + 2 && wy >= bottom - height) return obj;
    }
    return null;
  }

  private edgeExitAt(floor: number, x: number): MapObject | null {
    const level = this.game.level;
    return (this.game.location.objects ?? []).find((o) => {
      if (o.type !== "exit" || o.kind === "door" || !this.game.present(o)) return false;
      const p = level.objects.find((lo) => lo.id === o.id);
      return !!p && p.floor === floor && p.x === x;
    }) ?? null;
  }

  private onKey = (e: KeyboardEvent): void => {
    if (this.blocked) return;
    const k = e.key.toLowerCase();
    this.keys.add(k);
    if (k === "e" || k === " " || k === "enter") {
      e.preventDefault();
      const near = this.nearestObject();
      if (near) void this.interact(near);
    }
    if (["w", "s", "arrowup", "arrowdown"].includes(k)) this.climbKey(k === "w" || k === "arrowup" ? 1 : -1);
  };

  private onKeyUp = (e: KeyboardEvent): void => {
    this.keys.delete(e.key.toLowerCase());
  };

  private get blocked(): boolean {
    return this.paused || this.game.busy || !!this.game.state.ending;
  }

  private nearestObject(): MapObject | null {
    const level = this.game.level;
    let best: MapObject | null = null;
    let dist = 1.6;
    for (const obj of this.game.location.objects ?? []) {
      if (!this.game.present(obj) || (obj.type === "exit" && obj.kind !== "door")) continue;
      const p = level.objects.find((o) => o.id === obj.id);
      if (!p || p.floor !== this.hero.floor) continue;
      const d = Math.abs(p.x - this.hero.x);
      if (d < dist) [dist, best] = [d, obj];
    }
    return best;
  }

  private climbKey(dir: 1 | -1): void {
    const cell: Cell = [this.hero.floor, Math.round(this.hero.x)];
    const link = this.game.level.links.find((l) => {
      const [a, b] = [l.a, l.b] as unknown as [Cell, Cell];
      return (a[0] === cell[0] && a[1] === cell[1] && b[0] === cell[0] + dir) || (b[0] === cell[0] && b[1] === cell[1] && a[0] === cell[0] + dir);
    });
    if (link) {
      const [a, b] = [link.a, link.b] as unknown as [Cell, Cell];
      this.walkTo(a[0] === cell[0] ? b : a, null);
    }
  }

  // --- движение ---

  walkTo(goal: Cell, target: MapObject | null): void {
    const start: Cell = [this.hero.floor, Math.round(this.hero.x)];
    const path = findPath(this.game.level, start, goal);
    if (!path) return;
    // к NPC, сундуку и предмету подходим вплотную, но не встаём на их клетку
    if (target && ["npc", "chest", "thing"].includes(target.type) && path.length > 1) path.pop();
    this.path = path.slice(1);
    this.target = target;
    if (!this.path.length && target) void this.interact(target);
  }

  private async interact(obj: MapObject): Promise<void> {
    this.path = [];
    this.target = null;
    this.hero.anim = "idle";
    const placed = this.game.level.objects.find((o) => o.id === obj.id);
    if (placed && placed.x !== this.hero.x) this.hero.facing = placed.x > this.hero.x ? 1 : -1;
    const result = await this.game.interact(obj);
    if (result === "fled" && placed) {
      // отступаем на две клетки от врага
      const f = this.game.level.floors[this.hero.floor];
      const back = Math.min(f.x1, Math.max(f.x0, Math.round(this.hero.x) - 2 * Math.sign(placed.x - this.hero.x || 1)));
      this.hero.x = back;
      this.game.state.x = back;
    }
  }

  private step(dt: number): void {
    const level = this.game.level;
    const h = this.hero;
    if (!this.path.length && !this.blocked) {
      const dir = this.keys.has("a") || this.keys.has("arrowleft") ? -1 : this.keys.has("d") || this.keys.has("arrowright") ? 1 : 0;
      if (dir) {
        const f = level.floors[h.floor];
        const nx = Math.round(h.x) + dir;
        if (nx >= f.x0 && nx <= f.x1) this.path = [[h.floor, nx]];
        this.target = this.edgeExitAt(h.floor, nx);
      }
    }
    if (!this.path.length || this.blocked) {
      if (h.anim !== "idle" && !this.path.length) h.anim = "idle";
      return;
    }
    const [nf, nx] = this.path[0];
    if (nf !== h.floor) {
      // лестница: вертикальное движение к линии ног другого этажа
      const ty = feetY(level, nf);
      h.anim = "climb";
      const dy = ty - h.y;
      const move = CLIMB_SPEED * TILE * dt;
      if (Math.abs(dy) <= move) {
        h.y = ty;
        h.floor = nf;
        this.arrived();
      } else h.y += Math.sign(dy) * move;
      return;
    }
    const dx = nx - h.x;
    h.anim = "walk";
    h.facing = dx > 0 ? 1 : dx < 0 ? -1 : h.facing;
    const move = WALK_SPEED * dt;
    if (Math.abs(dx) <= move) {
      h.x = nx;
      this.arrived();
    } else h.x += Math.sign(dx) * move;
    this.checkFoes();
  }

  private arrived(): void {
    const h = this.hero;
    this.path.shift();
    Object.assign(this.game.state, { floor: h.floor, x: Math.round(h.x) });
    if (!this.path.length) {
      h.anim = "idle";
      const t = this.target;
      this.target = null;
      if (t) void this.interact(t);
    }
  }

  /** Касание врага на том же этаже запускает бой. */
  private checkFoes(): void {
    const level = this.game.level;
    for (const obj of this.game.location.objects ?? []) {
      if (obj.type !== "enemy" || !this.game.present(obj)) continue;
      const p = level.objects.find((o) => o.id === obj.id);
      if (p && p.floor === this.hero.floor && Math.abs(p.x - this.hero.x) < 0.9) {
        const side = Math.sign(this.hero.x - p.x) || -this.hero.facing;
        this.hero.x = p.x + side; // встаём на соседнюю с врагом клетку
        void this.interact(obj);
        return;
      }
    }
  }

  private followBuddy(dt: number): void {
    if (!this.game.companionPresent()) {
      this.buddy = null;
      return;
    }
    const h = this.hero;
    if (!this.buddy || this.buddy.floor !== h.floor || h.anim === "climb") {
      if (h.anim === "climb") return;
      this.buddy = { floor: h.floor, x: h.x - h.facing * 1.2, y: h.y, facing: h.facing, anim: "idle" };
      return;
    }
    const b = this.buddy;
    const goal = h.x - h.facing * 1.2;
    const dx = goal - b.x;
    if (Math.abs(dx) > 0.15) {
      b.x += Math.sign(dx) * Math.min(Math.abs(dx), WALK_SPEED * dt);
      b.facing = dx > 0 ? 1 : -1;
      b.anim = "walk";
    } else {
      b.anim = "idle";
      b.facing = h.facing;
    }
    b.y = h.y;
  }

  // --- рисование ---

  private loop = (ms: number): void => {
    if (this.stopped) return;
    const dt = Math.min(0.05, (ms - this.last) / 1000 || 0);
    this.last = ms;
    this.frame = ms / 1000;
    if (this.terrain) {
      this.step(dt);
      this.followBuddy(dt);
      this.centerCamera();
      this.draw();
    }
    requestAnimationFrame(this.loop);
  };

  private draw(): void {
    const ctx = this.ctx;
    const dpr = window.devicePixelRatio || 1;
    const s = this.scale * dpr;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#0e0c12";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    const camX = Math.round(this.cam.x * s) / s;
    const camY = Math.round(this.cam.y * s) / s;
    ctx.setTransform(s, 0, 0, s, -camX * s, -camY * s);

    const level = this.game.level;
    const loc = this.game.location;
    if (this.backdrop) {
      // параллакс: фон едет вдвое медленнее уровня
      const bg = this.backdrop.canvas;
      // фон закрывает всю высоту экрана, даже если уровень ниже экрана (телефон)
      const k = Math.max(1, Math.ceil(Math.max(this.terrain!.height, this.view.h) / bg.height));
      const w = bg.width * k;
      const top = this.terrain!.height - bg.height * k;
      const offset = camX * 0.5;
      const view = this.view;
      for (let x = camX - ((camX - offset) % w) - w; x < camX + view.w + w; x += w) ctx.drawImage(bg, Math.round(x), top, w, bg.height * k);
    }
    ctx.drawImage(this.terrain!, 0, 0);

    const t = this.frame;
    for (const obj of loc.objects ?? []) {
      if (!this.game.present(obj)) continue;
      const p = level.objects.find((o) => o.id === obj.id);
      if (!p) continue;
      const px = p.x * TILE + TILE / 2;
      const py = feetY(level, p.floor);
      if (obj.type === "exit" && obj.kind !== "door") drawEdgeMarker(ctx, level, p.floor, p.x, obj.kind === "left_edge");
      const arts: ObjectArt[] = objectArt(this.game.world.game, loc, level, obj, this.game.exitOpen(obj));
      arts.forEach((art, i) => drawArt(ctx, art, px + (i - (arts.length - 1) / 2) * 14, py, Math.floor(t * 2)));
      if (["npc", "thing", "chest"].includes(obj.type) && p.floor === this.hero.floor && Math.abs(p.x - this.hero.x) < 4) {
        const top = py - Math.max(...arts.map((a) => a.anchor[1]), TILE * 2) - 4 - Math.round(Math.sin(t * 4) * 1.5);
        ctx.fillStyle = "#f2d36b";
        ctx.beginPath();
        ctx.moveTo(px - 3, top - 4);
        ctx.lineTo(px + 3, top - 4);
        ctx.lineTo(px, top);
        ctx.fill();
      }
    }
    const heroSpec = this.game.world.game.hero;
    const ref = library.layout.walker.ref;
    const companion = this.game.world.companion();
    if (this.buddy && companion) this.drawMover(this.buddy, walkerFrames(companion.appearance, companion.id), ref, t);
    this.drawMover(this.hero, walkerFrames(heroSpec.appearance, heroSpec.id), ref, t);
  }

  private drawMover(m: Mover, frames: Record<Anim, HTMLCanvasElement[]>, ref: [number, number], t: number): void {
    const list = frames[m.anim];
    const i = m.anim === "climb" && this.path.length === 0 ? 0 : Math.floor(t * FPS[m.anim]) % list.length;
    drawArt(this.ctx, { frames: [list[i]], anchor: ref, flip: m.facing < 0 }, m.x * TILE + TILE / 2, m.y);
  }
}
