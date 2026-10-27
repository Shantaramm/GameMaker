// Сквозной тест (SPEC §12, этап 2б): проходит демо-игру кликами по экрану, как игрок.
//   npm run e2e               → оба прохождения
//   E2E_SHOTS=1 npm run e2e    → ещё и скриншоты ключевых моментов в docs/play/
// Координаты объектов берутся из отладочного хука window.__rpg.scene.screenPos(id), но клики — настоящие.

import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const shotsDir = fileURLToPath(new URL("../../docs/play/", import.meta.url));
const SHOTS = !!process.env.E2E_SHOTS;
const server = await createServer({ root, server: { port: 5195, strictPort: true }, logLevel: "error" });
await server.listen();
const BASE = "http://localhost:5195";
const browser = await chromium.launch();
if (SHOTS) await mkdir(shotsDir, { recursive: true });

function check(cond, message) {
  if (!cond) throw new Error(`проверка не прошла: ${message}`);
}

async function run(name, viewport, script) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("console", (m) => ["error", "warning"].includes(m.type()) && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  const g = helpers(page, name);
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

function helpers(page, name) {
  const visible = (sel) => page.locator(sel).first().isVisible();
  const state = () => page.evaluate(() => window.__rpg.controller.state);
  let shot = 0;

  const g = {
    state,
    async shot(label) {
      if (SHOTS) await page.screenshot({ path: `${shotsDir}${name}-${String(++shot).padStart(2, "0")}-${label}.png` });
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
      await page.goto(`${BASE}/play/demo?seed=${seed}`);
      await page.evaluate(() => localStorage.clear());
      await page.reload();
      await page.getByRole("button", { name: "Начать" }).click();
    },
  };
  const viewport = () => page.viewportSize();
  return g;
}

// --- прохождение 1: компьютер, хорошая концовка ---

await run("desktop-good-ending", { width: 1280, height: 720 }, async (g, page) => {
  await g.newGame("e2e-1");
  await g.talk();                                   // вступление пристани и сценка
  await g.shot("pier");

  await g.tap("tim_on_pier");
  await g.talk("Я рада тебя видеть", "Идём вместе.");
  let s = await g.state();
  check(s.flags.tim_joined && s.flags.trusted_tim && s.inventory.tonic === 1, "Тимофей присоединился и дал настойку");

  await g.tap("marfa_at_stall");
  await page.waitForSelector(".dlg:not(.hidden)");
  await page.locator(".dlg .choice", { hasText: "Что слышно в порту?" }).click();
  await g.shot("dialogue");
  await g.talk();
  await page.locator(".sheet-close").click();       // после разговора открылась лавка
  await g.tap("marfa_at_stall");
  await g.talk("Вы чем-то встревожены.");
  await page.waitForSelector(".sheet:not(.hidden)");
  await g.shot("shop");
  await page.locator(".shop-row", { hasText: "Разделочный нож" }).getByRole("button").click();
  await page.locator(".sheet-close").click();
  s = await g.state();
  check(s.inventory.fishing_knife === 1, "нож куплен");
  check(s.gold === 5, `золото после покупки: ${s.gold}`);

  await page.getByRole("button", { name: "Вещи" }).click();
  await page.locator(".inv-item", { hasText: "Разделочный нож" }).click();
  await page.getByRole("button", { name: "Надеть" }).click();
  check(await page.locator(".inv-nums", { hasText: "Атака 11" }).isVisible(), "нож добавил +2 к атаке (9 → 11)");
  await g.shot("inventory");
  await page.locator(".sheet-close").click();
  check((await g.state()).equipment.hand === "fishing_knife", "нож надет");

  await page.getByRole("button", { name: "Журнал" }).click();
  check(await page.locator(".quest", { hasText: "Крысы в сетях" }).isVisible(), "побочный квест в журнале");
  await page.locator(".sheet-close").click();

  await g.tap("pier_to_alley");
  await g.talk();                                   // вступление переулка
  check((await g.state()).location === "alley", "перешли в переулок");

  await g.tap("net_crates");                        // путь лежит через крыс
  check(await g.fight(), "победа над крысами");
  await g.idle();
  await g.tap("net_crates");
  await g.idle();
  s = await g.state();
  check(s.inventory.archive_key === 1 && s.defeated.includes("rats"), "ключ получен, крысы побеждены");

  await g.tap("alley_to_archive");
  await g.talk();
  check((await g.state()).location === "archive", "дверь архива открылась ключом");
  await g.tap("safe");                              // второй этаж: по лестнице
  await g.idle();
  s = await g.state();
  check(s.inventory.ledger === 1 && s.floor === 1, "сейф на втором этаже открыт");
  await g.shot("archive");

  // сохранение переживает перезагрузку
  await page.reload();
  await page.getByRole("button", { name: "Продолжить" }).click();
  await g.idle();
  s = await g.state();
  check(s.location === "archive" && s.inventory.ledger === 1 && s.equipment.hand === "fishing_knife", "сохранение после перезагрузки");

  await g.tap("efim_at_desk");
  await g.talk("Показать журнал Олеандра");
  check((await g.state()).skills.includes("salt_ward"), "выучен «Соляной круг»");

  await g.tap("archive_to_alley");
  await g.idle();
  await g.tap("alley_to_cliffs");
  await g.talk();
  await g.tap("cliffs_to_tower");                   // путь через служителей тумана
  check(await g.fight(), "победа у двери маяка");
  await g.idle();
  await g.tap("cliffs_to_tower");
  await g.talk();
  check((await g.state()).location === "tower", "вошли в башню");

  await page.getByRole("button", { name: "Журнал" }).click();
  check(await page.locator(".quest.complete", { hasText: "Зажечь маяк" }).isVisible(), "основной квест выполнен");
  await page.locator(".sheet-close").click();

  await g.tap("great_lens");                        // третий этаж
  await g.talk("Тим, держи линзу");
  await page.waitForSelector(".screen h1");
  await g.shot("ending");
  check((await page.locator(".screen h1").textContent()) === "Рассвет над бухтой", "хорошая концовка");
});

// --- прохождение 2: телефон, горькая концовка ---

await run("phone-bad-ending", { width: 375, height: 667 }, async (g, page) => {
  await g.newGame("e2e-2");
  await g.talk();
  await g.shot("pier");
  await g.tap("marfa_at_stall");
  await page.waitForSelector(".dlg:not(.hidden)");
  await page.locator(".dlg .choice", { hasText: "Что слышно в порту?" }).click();
  await g.shot("dialogue");
  await g.talk();
  await page.locator(".sheet-close").click();
  await g.tap("pier_to_alley");                     // Тимофея с собой не берём
  await g.talk();

  await g.tap("alley_to_archive");                  // к двери архива — через крыс
  check(await g.fight(), "победа над крысами");
  await g.idle();
  await g.tap("alley_to_archive");                  // дверь заперта: ключа ещё нет
  await page.waitForSelector(".dlg:not(.hidden)");
  check(await page.locator(".dlg-log", { hasText: "Нужно: Ключ от архива" }).isVisible(), "подсказка о ключе");
  await g.shot("locked");
  await g.talk();
  check((await g.state()).location === "alley", "запертая дверь не пустила");

  await g.tap("alley_to_cliffs");
  await g.talk();
  await g.tap("cliffs_to_tower");
  check(await g.fight(), "победа у двери маяка");
  await g.idle();
  await g.tap("cliffs_to_tower");
  await g.talk();
  await g.tap("great_lens");
  await page.waitForSelector(".dlg:not(.hidden)");
  check(await page.locator(".choice.locked", { hasText: "Тим, держи линзу" }).isVisible(), "вариант с Тимом недоступен");
  await g.shot("lens");
  await g.talk("Зажечь огонь в одиночку");
  await page.waitForSelector(".screen h1");
  await g.shot("ending");
  check((await page.locator(".screen h1").textContent()) === "Туман остаётся", "горькая концовка");
});

await browser.close();
await server.close();
