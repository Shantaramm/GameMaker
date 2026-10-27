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
      for (let i = 0; i < 12; i++) {
        if (await g.idle()) return; // по пути открылся бой или диалог
        const pos = await page.evaluate((id) => window.__rpg.scene.screenPos(id), objectId);
        check(pos, `объект ${objectId} не найден на уровне`);
        const vw = viewport().width;
        const vh = viewport().height;
        if (pos.x > 8 && pos.x < vw - 8 && pos.y > 40 && pos.y < vh - 4) {
          await page.mouse.click(pos.x, pos.y);
          return;
        }
        await page.mouse.click(Math.min(vw - 10, Math.max(10, pos.x)), Math.min(vh - 10, Math.max(60, pos.y)));
        await page.waitForTimeout(300);
      }
      throw new Error(`не удалось дотянуться до ${objectId}`);
    },
    /** Бой как у бота симулятора: лечение при HP < 30%, иначе навык, иначе атака. */
    async fight() {
      await page.waitForSelector(".battle:not(.hidden)", { timeout: 20000 });
      await g.shot("battle");
      for (let guard = 0; guard < 80; guard++) {
        const cont = page.getByRole("button", { name: "Продолжить" });
        if (await cont.isVisible()) {
          const won = await visible(".battle-result.win");
          await cont.click();
          return won;
        }
        const attack = page.locator(".battle-actions .btn", { hasText: "Атака" });
        if (!(await attack.isVisible()) || (await attack.isDisabled())) {
          await page.waitForTimeout(120);
          continue;
        }
        const s = await state();
        const low = await page.evaluate(() => {
          const c = window.__rpg.controller;
          return c.state.hp < 0.3 * (c.state.maxHp + 5);
        });
        const heals = Object.keys(s.inventory).filter((id) => id === "tonic");
        const btn = (text) => page.locator(".battle-actions .btn", { hasText: text });
        try {
          // бой мог закончиться между проверкой и кликом — тогда подменю не появится, начинаем заново
          if (low && heals.length) {
            await btn("Предмет").click({ timeout: 1500 });
            await btn("Бабушкина настойка").click({ timeout: 1500 });
          } else {
            await btn("Навык").click({ timeout: 1500 });
            const strike = btn("Точный удар");
            if (await strike.isEnabled({ timeout: 1500 })) await strike.click({ timeout: 1500 });
            else {
              await btn("Назад").click({ timeout: 1500 });
              await btn("Атака").click({ timeout: 1500 });
            }
          }
        } catch {
          // окно боя сменилось — следующая итерация разберётся
        }
        await page.waitForTimeout(150);
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
