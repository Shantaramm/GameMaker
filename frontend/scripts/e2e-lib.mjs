// Общие помощники сквозных тестов: клики по объектам карты, диалоги, бой.

import { chromium } from "playwright";
import { createServer } from "vite";

export async function startVite(root, port, env = {}) {
  Object.assign(process.env, env);
  const server = await createServer({ root, server: { port, strictPort: true }, logLevel: "error" });
  await server.listen();
  return server;
}

export async function launch() {
  return chromium.launch();
}

export function check(cond, message) {
  if (!cond) throw new Error(`проверка не прошла: ${message}`);
}

export async function run(browser, name, viewport, script, base, shotsDir = null) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("console", (m) => ["error", "warning"].includes(m.type()) && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  const g = helpers(page, name, base, shotsDir);
  const started = Date.now();
  try {
    await script(g, page);
  } catch (e) {
    await page.screenshot({ path: `e2e-fail-${name}.png` });
    throw new Error(`[${name}] ${e.message}\nскриншот: frontend/e2e-fail-${name}.png`);
  }
  check(errors.length === 0, `[${name}] ошибки в консоли:\n${errors.join("\n")}`);
  console.log(`✓ ${name} (${((Date.now() - started) / 1000).toFixed(1)} с)`);
  await page.close();
}

export function helpers(page, name, base, shotsDir = null) {
  const visible = (sel) => page.locator(sel).first().isVisible();
  const state = () => page.evaluate(() => window.__rpg.controller.state);
  let shot = 0;

  const g = {
    state,
    async shot(label) {
      if (shotsDir) await page.screenshot({ path: `${shotsDir}${name}-${String(++shot).padStart(2, "0")}-${label}.png` });
    },
    /** Ждёт, пока герой остановится или откроется окно (бой, диалог, панель). Возвращает true, если окно открыто. */
    async idle(timeout = 20000) {
      const h = await page.waitForFunction(() => {
        const r = window.__rpg;
        if (!r) return null;
        if (document.querySelector(".battle:not(.hidden), .dlg:not(.hidden), .sheet:not(.hidden)")) return "window";
        return !r.controller.busy && r.scene.path.length === 0 && r.scene.hero?.anim !== "walk" ? "idle" : null;
      }, null, { timeout });
      return (await h.jsonValue()) === "window";
    },
    /** Проходит открытый диалог: варианты — по порядку из choices, остальное — «Далее». */
    async talk(...choices) {
      await page.waitForSelector(".dlg:not(.hidden)", { timeout: 20000 });
      const queue = [...choices];
      for (let guard = 0; guard < 40; guard++) {
        if (!(await visible(".dlg:not(.hidden)"))) return;
        const next = page.getByRole("button", { name: "Далее ▸" });
        if (await next.isVisible()) {
          await next.click();
        } else {
          const want = queue.shift();
          check(want, "в диалоге варианты, а сценарий их не ожидал");
          await page.locator(".dlg .choice:not(.locked)", { hasText: want }).first().click();
        }
        await page.waitForTimeout(60);
      }
      throw new Error("диалог не закончился");
    },
    /** Тап по объекту на карте; если он за краем экрана — сначала идём в его сторону. */
    async tap(objectId) {
      const from = (await state()).location;
      for (let i = 0; i < 12; i++) {
        if (await g.idle()) return; // по пути открылся бой или диалог
        if ((await state()).location !== from) return; // шаг к краю экрана сам увёл через выход
        const pos = await page.evaluate((id) => window.__rpg.scene.screenPos(id), objectId);
        check(pos, `объект ${objectId} не найден на уровне`);
        const vw = viewport().width;
        const vh = viewport().height;
        if (pos.x > 8 && pos.x < vw - 8 && pos.y > 40 && pos.y < vh - 4) {
          await page.mouse.click(pos.x, pos.y);
          return;
        }
        // объект за краем экрана: шагаем в его сторону, но кликаем туда, где нет других объектов
        const step = await page.evaluate(({ x, y, vw, vh }) => {
          const scene = window.__rpg.scene;
          const cx = Math.min(vw - 10, Math.max(10, x));
          for (let cy = Math.min(vh - 10, Math.max(60, y)); cy < vh; cy += 12) {
            const [wx, wy] = scene.toWorld(cx, cy);
            if (!scene.hitObject(wx, wy)) return { x: cx, y: cy };
          }
          return { x: cx, y: Math.min(vh - 10, Math.max(60, y)) };
        }, { x: pos.x, y: pos.y, vw, vh });
        await page.mouse.click(step.x, step.y);
        await page.waitForTimeout(300);
      }
      throw new Error(`не удалось дотянуться до ${objectId}`);
    },
    /**
     * Тактический бой через интерфейс: за каждого бойца — выбрать его, подойти (спина → фланг → ближе, как бот
     * симулятора), при кураже купить «Сосредоточиться», ударить; лечиться при HP < 30%; затем «Конец хода».
     */
    async fight() {
      await page.waitForSelector(".battle:not(.hidden)", { timeout: 20000 });
      await page.waitForFunction(() => window.__battle, null, { timeout: 20000 });
      await g.shot("battle");
      const ready = () => page.waitForFunction(() => window.__battle && !window.__battle.busy(), null, { timeout: 60000 });
      const btn = (text) => page.locator(".battle-actions .btn", { hasText: text });
      const plan = () => page.evaluate(() => {
        const { battle: b, pointFor } = window.__battle;
        const u = b.aliveParty().find((p) => b.canAct(p));
        if (!u) return null;
        const dist = (f) => b.field.pathDist(u.pos, f.pos) ?? 1000 + Math.abs(u.pos[0] - f.pos[0]) + Math.abs(u.pos[1] - f.pos[1]);
        const foes = b.aliveEnemies().sort((a, c) => dist(a) - dist(c) || a.hp - c.hp);
        const target = foes[0];
        // навык — если хватает фокуса и он сильнее обычной атаки (как play_party_turn в simulator)
        const skills = window.__rpg.controller.world.skills;
        const dmgOf = (k) => (k.effect ?? []).reduce((s, e) => s + (e.damage ?? 0), 0);
        const strikes = u.skills.map((id) => skills.get(id)).filter((k) => k && k.target === "enemy" && dmgOf(k) > 0 && k.cost_focus <= u.focus);
        const best = strikes.sort((a, c) => dmgOf(c) - dmgOf(a))[0];
        const plain = Math.max(1, u.attack - Math.floor(target.defense / 2));
        const skill = best && dmgOf(best) > plain ? best.name : null;
        const reach = skill ? 3 : u.range;
        const cell = u.moved ? u.pos : b.bestCell(u, target, reach);
        const near = Math.abs(cell[0] - target.pos[0]) + Math.abs(cell[1] - target.pos[1]) <= reach;
        const focus = b.tactics.find((t) => t.id === "base_focus");
        return {
          id: u.id, index: b.party.indexOf(u), low: u.hp < u.maxHp * 0.3, near, skill,
          unit: pointFor(u.pos), move: cell[0] !== u.pos[0] || cell[1] !== u.pos[1] ? pointFor(cell) : null,
          target: target.id, tactic: !!focus && near && b.tacticOk(u, focus),
        };
      });
      const targetPoint = (id) => page.evaluate((id) => {
        const { battle: b, pointFor } = window.__battle;
        const t = b.enemies.find((e) => e.id === id);
        return t && t.hp > 0 ? pointFor(t.pos) : null;
      }, id);
      const deadline = Date.now() + 300_000;
      while (Date.now() < deadline) {
        await ready();
        if (await page.evaluate(() => window.__battle.finished())) {
          const won = await visible(".battle-result.win");
          if (process.env.E2E_BATTLE_LOG) console.log((await page.evaluate(() => window.__battle.battle.log.filter((e) => e.text).map((e) => e.text))).join("\n"));
          await page.getByRole("button", { name: "Продолжить" }).click();
          return won;
        }
        const p = await plan();
        if (!p) {
          await btn("Конец хода").click();
          continue;
        }
        if (p.unit) await page.mouse.click(p.unit.x, p.unit.y);
        await ready();
        if ((await page.evaluate(() => window.__battle.selected())) !== p.id) {
          // фигуру закрыл холм или сосед — выбираем бойца кнопкой в шапке, как сделал бы игрок
          await page.locator(".party-chips .chip").nth(p.index).click();
          await ready();
        }
        if (p.low && (await btn("Предмет").isEnabled())) {
          await btn("Предмет").click();
          const heal = page.locator(".battle-actions .btn:not(.btn-ghost)").first();
          await heal.click();
          await ready();
          if (await page.locator(".battle-actions .hint").isVisible()) await btn("Назад").click(); // это бомба, а не лечение
          else continue;
        }
        if (p.move) {
          await page.mouse.click(p.move.x, p.move.y);
          await ready();
        }
        if (p.tactic && (await btn("Тактика").isEnabled())) {
          await btn("Тактика").click();
          const focus = page.locator(".tactic", { hasText: "Сосредоточиться" });
          if (await focus.isEnabled()) await focus.click();
          else await btn("Назад").click();
          await ready();
        }
        const t = await targetPoint(p.target);
        const acted = await page.evaluate((id) => !window.__battle.battle.party.find((u) => u.id === id).acted, p.id);
        if (t && acted && p.near) {
          if (p.skill && (await btn("Навык").isEnabled())) {
            await btn("Навык").click();
            const skill = page.locator(".battle-actions .btn", { hasText: p.skill });
            if (await skill.isEnabled()) await skill.click();
            else await btn("Назад").click();
          }
          await page.mouse.click(t.x, t.y);
          await ready();
        }
        const still = await page.evaluate((id) => window.__battle && window.__battle.battle.canAct(window.__battle.battle.party.find((u) => u.id === id)), p.id);
        if (process.env.E2E_DEBUG) console.log("plan", JSON.stringify({ ...p, unit: undefined, move: !!p.move }), "selected", await page.evaluate(() => window.__battle?.selected()), "still", still);
        if (still) {
          if (await page.locator(".tactics").isVisible()) await btn("Назад").click();
          await btn("Защита").click();
        }
      }
      throw new Error("бой не закончился");
    },
    async newGame(seed) {
      await page.goto(`${base}/play/demo?seed=${seed}`);
      await page.evaluate(() => localStorage.clear());
      await page.reload();
      await page.getByRole("button", { name: "Начать" }).click();
    },
  };
  const viewport = () => page.viewportSize();
  return g;
}


/** Кратчайший путь к горькой концовке демо-игры от начала локации «Пристань». */
export async function playToFogEnding(g, page) {
  await g.tap("pier_to_alley");
  await g.talk();
  await g.tap("alley_to_cliffs");
  check(await g.fight(), "победа над крысами");
  await g.idle();
  await g.tap("alley_to_cliffs");
  await g.talk();
  await g.tap("cliffs_to_tower");
  check(await g.fight(), "победа у двери маяка");
  await g.idle();
  await g.tap("cliffs_to_tower");
  await g.talk();
  await g.tap("great_lens");
  await g.talk("Зажечь огонь в одиночку");
  await page.waitForSelector(".screen h1");
}
