// Сквозной путь пользователя (SPEC §12, этап 6): идея → бриф → генерация → игра → концовка →
// ссылка открывается в другом браузере и игра начинается с начала.
//   npm run e2e:site   (поднимает бэкенд на демо-провайдере сам: uvicorn + временная база)

import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { check, helpers, launch, playToFogEnding, startVite } from "./e2e-lib.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const backendDir = fileURLToPath(new URL("../../backend/", import.meta.url));
const API_PORT = 8011;
const dataDir = await mkdtemp(join(tmpdir(), "rpg-e2e-"));
const shotsDir = process.env.E2E_SHOTS ? fileURLToPath(new URL("../../docs/play/", import.meta.url)) : null;
const shot = async (page, name) => shotsDir && page.screenshot({ path: `${shotsDir}site-${name}.png` });

const api = spawn(join(backendDir, ".venv/bin/uvicorn"), ["app.main:app", "--port", String(API_PORT), "--log-level", "warning"], {
  cwd: backendDir,
  env: { ...process.env, DATA_DIR: dataDir, LLM_PROVIDER: "demo", GIGACHAT_AUTH_KEY: "" },
  stdio: ["ignore", "inherit", "inherit"],
});
const cleanup = async () => {
  api.kill();
  await rm(dataDir, { recursive: true, force: true });
};

async function waitForApi() {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${API_PORT}/api/info`)).ok) return;
    } catch {
      // ещё стартует
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("бэкенд не запустился");
}

let server;
let browser;
try {
  await waitForApi();
  server = await startVite(root, 5193, { API_URL: `http://127.0.0.1:${API_PORT}` });
  const BASE = "http://localhost:5193";
  browser = await launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => ["error", "warning"].includes(m.type()) && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  const started = Date.now();

  // главная → бриф
  await page.goto(BASE);
  await page.waitForSelector(".banner");
  check((await page.locator(".banner").textContent()).includes("Демо-режим"), "предупреждение о демо-режиме");
  await page.locator(".example").first().click();
  check((await page.locator("textarea.idea").inputValue()).startsWith("Юная травница"), "пример подставился в поле");
  await shot(page, "1-home");
  await page.getByRole("button", { name: "Развернуть в бриф" }).click();
  await page.waitForURL("**/brief");
  check(await page.locator(".questions li").count() >= 2, "уточняющие вопросы над брифом");
  check((await page.locator("textarea.brief").inputValue()).includes("Погасший маяк"), "бриф в поле");

  // бриф → генерация
  await shot(page, "2-brief");
  await page.getByRole("button", { name: "Создать игру" }).click();
  await page.waitForURL("**/progress/*");
  const gameId = page.url().split("/progress/")[1];
  await page.waitForSelector(".hero-card", { timeout: 30000 });
  check(await page.locator(".hero-card").count() >= 4, "герои показаны во время генерации");
  await shot(page, "3-progress");
  await page.getByRole("button", { name: "Играть ▸" }).click({ timeout: 60000 });
  await page.waitForURL(`**/play/${gameId}`);
  // та же игра с фиксированным сидом: бои детерминированы, а ссылка «Поделиться» query не содержит
  await page.goto(`${BASE}/play/${gameId}?seed=site`);

  // игра → концовка
  await page.getByRole("button", { name: "Начать" }).click();
  const g = helpers(page, "site", BASE);
  await g.talk();
  await playToFogEnding(g, page);
  check((await page.locator(".screen h1").textContent()) === "Туман остаётся", "концовка");
  await page.getByRole("button", { name: "Поделиться" }).click();
  await page.waitForSelector("text=Ссылка скопирована.");
  const link = await page.evaluate(() => navigator.clipboard.readText());
  check(link === `${BASE}/play/${gameId}`, `ссылка: ${link}`);

  // автор публикует игру прямо с экрана концовки → она в каталоге «Готовые игры»
  await page.getByRole("button", { name: "Опубликовать в каталоге" }).click();
  await page.waitForSelector("text=Игра в каталоге «Готовые игры».");
  await page.goto(`${BASE}/games`);
  await page.waitForSelector(".game-card");
  const featured = await page.locator(".game-grid").first().locator(".game-card h3").allTextContents();
  check(featured.join("|") === "Погасший маяк|Последнее письмо перед снегом|Последняя смена", `подборка: ${featured}`);
  const community = page.locator(".game-grid").nth(1).locator(".game-card");
  check(await community.count() === 1 && (await community.locator(".badge").textContent()) === "ваша", "игра автора среди игр игроков");
  check(await page.locator(".my-game", { hasText: "Погасший маяк" }).getByRole("button", { name: "Скрыть из каталога" }).isVisible(), "в «Моих играх» можно скрыть");
  await shot(page, "4-catalog");
  await page.locator(".game-card", { hasText: "Последнее письмо перед снегом" }).getByRole("link", { name: "Играть ▸" }).click();
  await page.waitForURL("**/play/postman");
  await page.waitForSelector(".screen h1");
  check((await page.locator(".screen h1").textContent()) === "Последнее письмо перед снегом", "игра из подборки открылась");

  // ссылка в другом браузере: игра с начала, без чужого сохранения
  const other = await browser.newContext({ viewport: { width: 375, height: 667 } });
  const page2 = await other.newPage();
  await page2.goto(link);
  await page2.waitForSelector(".screen h1");
  check((await page2.locator(".screen h1").textContent()) === "Погасший маяк", "название игры по ссылке");
  check(!(await page2.getByRole("button", { name: "Продолжить" }).isVisible()), "в другом браузере нет сохранения");
  await page2.getByRole("button", { name: "Начать" }).click();
  await page2.waitForSelector(".dlg:not(.hidden)");
  check((await page2.evaluate(() => window.__rpg.controller.state.location)) === "pier", "игра началась с первой локации");
  await page2.goto(`${BASE}/games`);
  await page2.waitForSelector(".game-card");
  check(await page2.locator(".game-grid").nth(1).locator(".game-card").count() === 1, "чужой браузер видит опубликованную игру");
  check(!(await page2.locator(".my-games").isVisible()) && !(await page2.locator(".badge").isVisible()), "но не может её скрыть");
  await page2.screenshot(shotsDir ? { path: `${shotsDir}site-5-catalog-phone.png`, fullPage: true } : {});

  // профиль «без боёв, глубокие диалоги» на телефоне: бриф и игра — про разговоры, без врагов
  await page2.goto(BASE);
  await page2.waitForSelector(".profile");
  await page2.getByRole("radio", { name: "Без боёв" }).click();
  await page2.getByRole("radio", { name: "Глубокие" }).click();
  check(await page2.locator(".profile", { hasText: "Disco Elysium" }).isVisible(), "подсказка к глубоким диалогам");
  await page2.locator("textarea.idea").fill("Ночной сторож музея замечает, что картину подменили, и до утра решает, что дороже: правда или люди.");
  if (shotsDir) await page2.screenshot({ path: `${shotsDir}site-6-profile-phone.png`, fullPage: true });
  await page2.getByRole("button", { name: "Развернуть в бриф" }).click();
  await page2.waitForURL("**/brief");
  check((await page2.locator("textarea.brief").inputValue()).startsWith("# Последняя смена"), "бриф под профиль без боёв");
  await page2.getByRole("button", { name: "Создать игру" }).click();
  await page2.getByRole("button", { name: "Играть ▸" }).click({ timeout: 60000 });
  await page2.waitForSelector(".screen h1");
  check((await page2.locator(".screen h1").textContent()) === "Последняя смена", "игра без боёв собралась");

  check(errors.length === 0, `ошибки в консоли:\n${errors.join("\n")}`);
  console.log(`✓ идея → бриф → генерация → игра → концовка → ссылка (${((Date.now() - started) / 1000).toFixed(1)} с)`);
} finally {
  await browser?.close();
  await server?.close();
  await cleanup();
}
