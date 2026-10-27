// Показательные кадры тактического боя для docs/play/: начало, ход, удар в спину, тактики, ход врагов.
//   node scripts/battle-shots.mjs   (поднимает Vite сам)
import { fileURLToPath } from "node:url";
import { helpers, launch, startVite } from "./e2e-lib.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const out = fileURLToPath(new URL("../../docs/play/", import.meta.url));
const server = await startVite(root, 5197);
const BASE = "http://localhost:5197";
const browser = await launch();
try {
  for (const [w, h, name] of [[1280, 720, "battle-desktop"], [375, 667, "battle-phone"]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    const g = helpers(page, name, BASE);
    const shot = (label) => page.screenshot({ path: `${out}${name}-${label}.png` });
    await g.newGame("shots");
    await g.talk();
    if (w > 400) {
      // на телефоне Тимофея загораживает Марфа — там бой в одиночку
      await g.tap("tim_on_pier");
      await g.talk("Я рада тебя видеть", "Идём вместе.");
    }
    await g.tap("pier_to_alley");
    await g.talk();
    await g.tap("alley_to_cliffs");
    await g.fight();
    await g.idle();
    await g.tap("alley_to_cliffs");
    await g.talk();
    await g.tap("cliffs_to_tower");
    await page.waitForFunction(() => window.__battle);
    await page.waitForTimeout(350);
    await shot("1-start");
    await page.waitForTimeout(1200);
    await shot("2-move");   // герой выбран: синие клетки — куда можно пойти
    // первый ход: тактики видны, затем ход врагов — они подходят
    await page.locator(".battle-actions .btn", { hasText: "Тактика" }).click();
    await page.waitForTimeout(200);
    await shot("3-tactics");
    await page.locator(".battle-actions .btn", { hasText: "Назад" }).click();
    await page.locator(".battle-actions .btn", { hasText: "Конец хода" }).click();
    await page.waitForTimeout(450);
    await shot("4-enemy-turn");
    await page.waitForFunction(() => !window.__battle.busy(), null, { timeout: 30000 });
    // второй ход: встаём туда, откуда враг достаётся сбоку или в спину, — над ним подпись с уроном
    const plan = await page.evaluate(() => {
      const { battle: b, pointFor } = window.__battle;
      const u = b.hero();
      let best = null;
      for (const t of b.aliveEnemies()) {
        for (const r of b.moves(u).values()) {
          if ((b.unitAt(r.cell) && b.unitAt(r.cell) !== u) || Math.abs(r.cell[0] - t.pos[0]) + Math.abs(r.cell[1] - t.pos[1]) > u.range) continue;
          const side = b.preview(u, t, r.cell).side;
          const score = side === "back" ? 0 : side === "flank" ? 1 : 2;
          if (!best || score < best.score) best = { score, cell: r.cell, target: t.id };
        }
      }
      if (!best) return null;
      const here = best.cell[0] === u.pos[0] && best.cell[1] === u.pos[1];
      return { move: here ? null : pointFor(best.cell), target: best.target };
    });
    if (plan) {
      if (plan.move) await page.mouse.click(plan.move.x, plan.move.y);
      await page.waitForFunction(() => !window.__battle.busy());
      await page.waitForTimeout(250);
      await shot("5-preview");
      const t = await page.evaluate((id) => {
        const { battle: b, pointFor } = window.__battle;
        return pointFor(b.enemies.find((x) => x.id === id).pos);
      }, plan.target);
      await page.mouse.click(t.x, t.y);
      await page.waitForTimeout(300);
      await shot("6-hit");
    }
    await page.close();
  }
} finally {
  await browser.close();
  await server.close();
}
