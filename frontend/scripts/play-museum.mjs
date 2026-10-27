// Прохождение «Последней смены» (игра без боёв, глубокие диалоги) кликами до концовки.
//   node scripts/play-museum.mjs   (сайт и API уже запущены; PHONE=1 — 375×667; SEED — сид бросков)
// Броски кубиков случайны, поэтому сценарий адаптивный: в каждом разговоре выбирает первый доступный вариант
// из списка предпочтений, а концовку — по тому, что удалось узнать.
import { check, helpers, launch } from "./e2e-lib.mjs";

const BASE = process.env.BASE ?? "http://localhost:5173";
const shotsDir = process.env.E2E_SHOTS ?? null;
const phone = !!process.env.PHONE;
const viewport = phone ? { width: 375, height: 667 } : { width: 1280, height: 720 };
const name = phone ? "museum-phone" : "museum";
const browser = await launch();
const page = await browser.newPage({ viewport });
const errors = [];
page.on("console", (m) => ["error", "warning"].includes(m.type()) && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(e.stack ?? String(e)));
const g = helpers(page, name, BASE, shotsDir);
const state = () => g.state();
const rolls = { ok: 0, fail: 0 };

/** Разговор: «Далее» или первый доступный вариант из prefs; если таких нет — последний доступный (обычно «уйти»). */
async function converse(prefs, shotAt = null) {
  await page.waitForSelector(".dlg:not(.hidden)", { timeout: 20000 });
  for (let guard = 0; guard < 60; guard++) {
    if (!(await page.locator(".dlg:not(.hidden)").isVisible())) return;
    const next = page.getByRole("button", { name: "Далее ▸" });
    if (await next.isVisible()) {
      await next.click();
    } else {
      const options = page.locator(".dlg .choice:not(.locked)");
      const texts = await options.allTextContents();
      if (shotAt && texts.some((t) => t.includes(shotAt))) {
        await g.shot("checks");
        shotAt = null;
      }
      let index = -1;
      for (const p of prefs) {
        index = texts.findIndex((t) => t.includes(p));
        if (index >= 0) break;
      }
      if (index < 0) index = texts.length - 1;
      const before = await page.locator(".dlg-log .roll").count();
      await options.nth(index).click();
      await page.waitForTimeout(150);
      if ((await page.locator(".dlg-log .roll").count()) > before) {
        await page.waitForTimeout(1100); // кубики докрутились
        const last = await page.locator(".dlg-log .roll").last().textContent();
        last.includes("УСПЕХ") ? rolls.ok++ : rolls.fail++;
      }
    }
    await page.waitForTimeout(90);
  }
  throw new Error("разговор не закончился");
}
const talkTo = async (id, prefs, shotAt) => {
  await g.tap(id);
  await converse(prefs, shotAt);
  await g.idle();
};
const go = async (exit, to) => {
  for (let i = 0; i < 4 && (await state()).location !== to; i++) {
    await g.tap(exit);
    await page.waitForTimeout(300);
    if ((await state()).location !== to && (await page.locator(".dlg:not(.hidden)").isVisible())) await converse([]);
    await g.idle().catch(() => {});
  }
  check((await state()).location === to, `переход ${exit} → ${to}`);
  if (await page.locator(".dlg:not(.hidden)").isVisible()) await converse([]);
  await g.idle();
};

try {
  await page.goto(`${BASE}/play/museum?seed=${process.env.SEED ?? "museum"}`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector(".screen h1");
  check((await page.locator(".screen h1").textContent()) === "Последняя смена", "титул");
  await page.getByRole("button", { name: "Начать" }).click();
  await converse([]);                                          // вступление и голоса Эрудиции и Самообладания
  await g.idle();
  check(!(await page.locator(".hud .bar-focus").count()), "в игре без боёв нет фокуса в HUD");

  await talkTo("nina_in_cloakroom", ["недоговариваете", "Вы не верите", "Новая рама", "Спасибо. Я осторожно"], "недоговариваете");
  await g.tap("cloakroom_box");
  await g.idle();
  await go("lobby_to_gallery", "gallery");
  await talkTo("the_painting", ["мазкам", "каталогах", "Запомнить", "Платок"]);
  await talkTo("ira_in_gallery", ["плакали", "Учителю", "написали копию", "Пойдёмте со мной"]);
  await g.shot("gallery");
  await talkTo("window_bench", ["Вспомнить, зачем"]);
  check((await state()).inner.will >= 3, "скамья у окна: Самообладание выросло");

  await go("gallery_to_restoration", "restoration");
  await g.tap("ira_notebook");
  await converse([]);
  await g.idle();
  for (let i = 0; i < 2 && !(await state()).flags.forgery_proven; i++) {
    if ((await state()).examined.includes("easel") && i > 0) break;
    await talkTo("easel", ["Сопоставить", "надписи", "Сфотографировать", "Это доказательство"]);
  }
  await talkTo("frames_crate", ["ключом Нины", "Поддеть", "Подождать", "Взять картину"]);
  await g.shot("crate");

  // очки навыков: лист героя и «+» — в Самообладание, чтобы выдержать разговор с директором
  if ((await state()).skillPoints > 0) {
    await page.getByRole("button", { name: /^Герой/ }).click();
    await page.waitForSelector(".skills-sheet");
    await g.shot("skills");
    const will = page.locator(".skill", { hasText: "Самообладание" }).getByRole("button", { name: "+" });
    if (await will.isVisible()) await will.click();
    await page.locator(".sheet-close").click();
  }

  await go("restoration_to_gallery", "gallery");
  await go("gallery_to_lobby", "lobby");
  await go("lobby_to_director", "director_office");
  await talkTo("opening_photo", []);
  await talkTo("director_at_desk", ["Давайте", "Понимаю", "Просто сказать", "мальчик с фотографии", "Повешу", "Покажите документы"], "Просто сказать");
  await go("director_to_lobby", "lobby");
  await go("lobby_to_yard", "yard");
  await talkTo("grisha_at_truck", ["Сколько ящиков"]);

  const s = await state();
  const [exit, title] = s.flags.director_confessed && s.flags.original_found ? ["yard_return", "Утро над Сурой"]
    : s.flags.forgery_proven ? ["yard_call", "Правда"] : ["yard_leave", "Красивая ложь"];
  await g.tap(exit);
  await page.waitForSelector(".screen h1", { timeout: 30000 });
  check((await page.locator(".screen h1").textContent()) === title, `концовка «${title}»`);
  await g.shot("ending");
  check(errors.length === 0, `ошибки в консоли:\n${errors.join("\n")}`);
  console.log(`✓ ${name}: концовка «${title}», проверок: ${rolls.ok} успехов, ${rolls.fail} провалов, уровень ${s.level}`);
} catch (e) {
  await page.screenshot({ path: `e2e-fail-${name}.png` });
  console.error(e.message);
  console.error(errors.join("\n"));
  process.exitCode = 1;
} finally {
  await browser.close();
}
