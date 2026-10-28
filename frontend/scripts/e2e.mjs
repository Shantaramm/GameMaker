// Сквозной тест (SPEC §12, этап 2б): проходит демо-игру кликами по экрану, как игрок.
//   npm run e2e               → оба прохождения
//   E2E_SHOTS=1 npm run e2e    → ещё и скриншоты ключевых моментов в docs/play/
// Координаты объектов берутся из отладочного хука window.__rpg.scene.screenPos(id), но клики — настоящие.

import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { check, launch, run as runCase, startVite } from "./e2e-lib.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const shotsDir = process.env.E2E_SHOTS ? fileURLToPath(new URL("../../docs/play/", import.meta.url)) : null;
const server = await startVite(root, 5195);
const BASE = "http://localhost:5195";
const browser = await launch();
if (shotsDir) await mkdir(shotsDir, { recursive: true });
const run = (name, viewport, script) => runCase(browser, name, viewport, script, BASE, shotsDir);

// --- прохождение 1: компьютер, хорошая концовка ---

await run("desktop-good-ending", { width: 1280, height: 720 }, async (g, page) => {
  await g.newGame("e2e-1");
  await g.talk();                                   // вступление пристани и сценка
  await page.keyboard.down("d");                    // пара шагов к Тимофею — он бормочет над головой (§5.11)
  await page.waitForTimeout(2000);
  await page.keyboard.up("d");
  await page.waitForFunction(() => [...document.querySelectorAll(".bark")].some((b) => Number(b.style.opacity) > 0.5), null, { timeout: 10000 });
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

  await page.getByRole("button", { name: /^Герой/ }).click();
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
