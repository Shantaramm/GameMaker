// Прохождение сгенерированной через ретранслятор игры «Последнее письмо перед снегом» кликами до хорошей концовки.
//   GAME_ID=… node scripts/play-postman.mjs  (сайт и API уже запущены)
import { check, helpers, launch } from "./e2e-lib.mjs";

const BASE = process.env.BASE ?? "http://localhost:5173";
const id = process.env.GAME_ID;
const shotsDir = process.env.E2E_SHOTS ?? null;
const viewport = process.env.PHONE ? { width: 375, height: 667 } : { width: 1280, height: 720 };
const name = process.env.PHONE ? "postman-phone" : "postman";
const browser = await launch();
const page = await browser.newPage({ viewport });
const errors = [];
page.on("console", (m) => ["error", "warning"].includes(m.type()) && errors.push(m.text()));
page.on("pageerror", (e) => { errors.push(e.stack ?? String(e)); page.screenshot({ path: `e2e-pageerror-${errors.length}.png` }).catch(() => {}); });
const g = helpers(page, name, BASE, shotsDir);
const started = Date.now();
const where = async () => (await g.state()).location;
// случайно открытый диалог: «Далее» или последний доступный вариант (обычно «уйти»)
const dismiss = async () => {
  for (let i = 0; i < 30 && (await page.locator(".dlg:not(.hidden)").isVisible()); i++) {
    const next = page.getByRole("button", { name: "Далее ▸" });
    if (await next.isVisible()) await next.click();
    else await page.locator(".dlg .choice:not(.locked)").last().click();
    await page.waitForTimeout(80);
  }
  if (await page.locator(".sheet:not(.hidden)").isVisible()) await page.locator(".sheet-close").first().click();
};
const go = async (exit, to) => {
  for (let i = 0; i < 4 && (await where()) !== to; i++) {
    await g.tap(exit);
    await page.waitForTimeout(300);
    // тап мог попасть в соседний предмет — дочитываем его и пробуем снова
    if ((await where()) !== to && (await g.idle()) && (await page.locator(".dlg:not(.hidden)").isVisible())) await dismiss();
    await g.idle().catch(() => {});
  }
  check((await where()) === to, `переход ${exit} → ${to}`);
  if (await g.idle()) await g.talk(); // вступление при первом входе
};
const inBattle = () => page.locator(".battle:not(.hidden)").isVisible();
// тап по объекту; если по пути герой задел врага — сначала бой, потом снова к объекту
const reach = async (objectId) => {
  for (let i = 0; i < 3; i++) {
    await g.tap(objectId);
    await page.waitForTimeout(200);
    await g.idle();
    if (!(await inBattle())) return;
    check(await g.fight(), `победа по пути к ${objectId}`);
    await g.idle();
  }
};
const fight = async (foe) => {
  await g.tap(foe);
  check(await g.fight(), `победа: ${foe}`);
  await g.idle();
};
try {
  await page.goto(`${BASE}/play/${id}`);
  await page.waitForSelector(".screen h1");
  check((await page.locator(".screen h1").textContent()) === "Последнее письмо перед снегом", "титул");
  await g.shot("title");
  await page.getByRole("button", { name: "Начать" }).click();
  await g.talk();
  await g.shot("village");

  await g.tap("mother_at_post");
  await g.shot("mother");
  await g.talk("Давай, мама. Донесу.");
  check((await g.state()).inventory.petition_letter, "письмо в сумке");
  await g.tap("gordey_on_square");
  await g.talk("А вы сами видели этот обвал?");

  await go("village_to_trail", "trail");
  await reach("zlata_on_ledge");
  await g.shot("zlata");
  await g.talk("Пойдём вместе. Мне всё равно туда.");
  await reach("hunter_cache");
  if (!(await g.state()).defeated.includes("wolf_pack")) await fight("wolf_pack");
  await g.shot("after-wolves");

  await go("trail_to_outpost", "outpost");
  await fight("outpost_guards");
  await g.tap("guard_tent_chest");
  await g.idle();
  await g.tap("salt_crate_pile");
  await g.idle();
  check((await g.state()).inventory.salt_crate, "соль найдена");

  await go("outpost_to_trail", "trail");
  await go("trail_to_village", "village");
  await g.tap("vera_at_shop");
  await g.talk("Вот твоя соль, Вера. Нашёл на заставе.");
  await page.waitForSelector(".sheet:not(.hidden)");
  await g.shot("shop");
  await page.locator(".sheet-close").first().click();
  check((await g.state()).inventory.gordey_key, "ключ от чердака");

  await go("village_to_house", "headman_house");
  await g.tap("headman_desk");
  await g.talk();
  await g.tap("attic_chest");
  await g.idle();
  await g.shot("attic");
  check((await g.state()).inventory.smuggler_ledger, "долговая книга");
  await go("house_to_village", "village");

  await go("village_to_trail", "trail");
  await go("trail_to_outpost", "outpost");
  await go("outpost_to_pass", "pass");
  await fight("yakov_band");
  await g.tap("yakov_beaten");
  await g.shot("yakov");
  await g.talk("Поверят. У меня долговая книга Гордея.");
  await g.tap("pass_to_city_witness");
  await page.waitForSelector(".screen h1", { timeout: 30000 });
  check((await page.locator(".screen h1").textContent()) === "Дорога открыта", "хорошая концовка");
  await g.shot("ending");
  check(errors.length === 0, `ошибки в консоли:\n${errors.join("\n")}`);
  console.log(`✓ ${name}: до концовки «Дорога открыта» (${((Date.now() - started) / 1000).toFixed(1)} с), локация ${await where().catch(() => "-")}`);
} catch (e) {
  await page.screenshot({ path: `e2e-fail-${name}.png` });
  console.error(e.message);
  console.error(errors.join("\n"));
  process.exitCode = 1;
} finally {
  await browser.close();
}
