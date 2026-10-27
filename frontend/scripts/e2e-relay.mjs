// Генерация через ретранслятор (LLM_PROVIDER=relay): идея → бриф → генерация на живом сайте.
// Ответы на запросы пайплайна пишет оператор в data/relay/…; скрипт ждёт до часа.
//   node scripts/e2e-relay.mjs "идея"   (сайт и API уже запущены: npm run dev + uvicorn)
// Печатает id игры; дальше игру проходит отдельный сценарий.

import { writeFile } from "node:fs/promises";
import { check, launch } from "./e2e-lib.mjs";

const BASE = process.env.BASE ?? "http://localhost:5173";
const idea = process.argv[2];
const shots = process.env.E2E_SHOTS ?? null;
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on("console", (m) => ["error", "warning"].includes(m.type()) && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE);
  await page.locator("textarea.idea").fill(idea);
  await page.getByRole("button", { name: "Развернуть в бриф" }).click();
  await page.waitForURL("**/brief", { timeout: 3600_000 });
  if (shots) await page.screenshot({ path: `${shots}relay-1-brief.png`, fullPage: true });
  await page.getByRole("button", { name: "Создать игру" }).click();
  await page.waitForURL("**/progress/*");
  const gameId = page.url().split("/progress/")[1];
  console.log(`game_id: ${gameId}`);
  await writeFile(process.env.GAME_ID_FILE ?? "relay-game-id.txt", gameId);
  await page.waitForSelector(".hero-card", { timeout: 3600_000 });
  if (shots) await page.screenshot({ path: `${shots}relay-2-progress.png`, fullPage: true });
  await page.getByRole("button", { name: "Играть ▸" }).waitFor({ timeout: 3600_000 });
  if (shots) await page.screenshot({ path: `${shots}relay-3-ready.png`, fullPage: true });
  check(errors.length === 0, `ошибки в консоли:\n${errors.join("\n")}`);
  console.log("✓ игра готова");
} finally {
  await browser.close();
}
