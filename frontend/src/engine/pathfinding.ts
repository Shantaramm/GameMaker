// Поиск пути по этажам и лестницам — та же логика, что find_path в backend/app/engine/levels.py.

import type { Level } from "../types/game";

export type Cell = [number, number]; // [этаж, x]

function links(level: Level): [Cell, Cell][] {
  return level.links.map((l) => [l.a as unknown as Cell, l.b as unknown as Cell]);
}

export function neighbors(level: Level, [floor, x]: Cell): Cell[] {
  const f = level.floors[floor];
  const out: Cell[] = [];
  for (const nx of [x - 1, x + 1]) if (nx >= f.x0 && nx <= f.x1) out.push([floor, nx]);
  for (const [a, b] of links(level)) {
    if (a[0] === floor && a[1] === x) out.push(b);
    else if (b[0] === floor && b[1] === x) out.push(a);
  }
  return out;
}

const key = ([f, x]: Cell) => `${f}:${x}`;

/** Кратчайший путь (BFS), включая старт и цель; null — недостижимо. */
export function findPath(level: Level, start: Cell, goal: Cell): Cell[] | null {
  const prev = new Map<string, Cell | null>([[key(start), null]]);
  const queue: Cell[] = [start];
  while (queue.length) {
    const cell = queue.shift()!;
    if (cell[0] === goal[0] && cell[1] === goal[1]) {
      const path: Cell[] = [cell];
      let p = prev.get(key(cell));
      while (p) {
        path.push(p);
        p = prev.get(key(p));
      }
      return path.reverse();
    }
    for (const n of neighbors(level, cell)) {
      if (!prev.has(key(n))) {
        prev.set(key(n), cell);
        queue.push(n);
      }
    }
  }
  return null;
}

export function spawnFor(level: Level, cameFrom: string | null): Cell {
  const s = level.spawns.find((sp) => sp.from === cameFrom) ?? level.spawns.find((sp) => sp.from === "default")!;
  return [s.floor, s.x];
}
