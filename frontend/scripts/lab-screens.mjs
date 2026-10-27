// Скриншоты PixelLab для ручной оценки библиотеки (SPEC §12, этап 2а).
//   npm run screens            → docs/lab/*.png
//   SEED=7 npm run screens     → другой набор случайных портретов и фонов

import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const out = fileURLToPath(new URL("../../docs/lab/", import.meta.url));
const seed = process.env.SEED ?? "1";

const server = await createServer({ root, server: { port: 5199, strictPort: true }, logLevel: "error" });
await server.listen();
const base = "http://localhost:5199";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
const errors = [];
page.on("console", (m) => (m.type() === "error" || m.type() === "warning") && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await mkdir(out, { recursive: true });

async function shot(url, file, selector, width = 1100) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(base + url);
  await page.waitForSelector(selector);
  await page.locator(selector).first().screenshot({ path: out + file });
  console.log(`docs/lab/${file}`);
}

await shot(`/lab?grid=portraits&seed=${seed}&count=20`, "portraits.png", ".grid-page[data-ready]", 1000);
await shot(`/lab?grid=backgrounds&seed=${seed}&count=10`, "backgrounds.png", ".grid-page[data-ready]", 1000);
await shot(`/lab?grid=creatures&seed=${seed}&count=12`, "creatures.png", ".grid-page[data-ready]", 1000);
await shot("/lab?tab=0", "lab-portrait.png", "main");
await shot("/lab?tab=3", "lab-demo-game.png", "main");

await browser.close();
await server.close();

if (errors.length) {
  console.error("Ошибки и предупреждения в консоли:\n" + errors.join("\n"));
  process.exit(1);
}
