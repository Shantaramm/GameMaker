// Скриншоты PixelLab для ручной оценки библиотеки (SPEC §12, этап 2а).
//   npm run screens            → docs/lab/*.png
//   SEED=7 npm run screens     → другой набор случайных портретов и фонов

import { mkdir, rename, rm } from "node:fs/promises";
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
await shot(`/lab?grid=walkers&seed=${seed}&count=20`, "walkers.png", ".grid-page[data-ready]", 1000);
await shot("/lab?grid=levels&count=5", "levels.png", ".grid-page[data-ready]", 1300);
await shot("/lab?tab=4", "lab-tilesets.png", "main");
await shot("/lab?tab=6", "lab-icons.png", "main");
await shot("/lab?tab=0", "lab-portrait.png", "main");
await shot("/lab?tab=3", "lab-demo-game.png", "main");

// Видео ходьбы: 20 случайных персонажей, ~3 секунды.
const videoDir = out + "video-tmp/";
const recorder = await browser.newContext({ viewport: { width: 760, height: 560 }, recordVideo: { dir: videoDir, size: { width: 760, height: 560 } } });
const vpage = await recorder.newPage();
await vpage.goto(`${base}/lab?grid=walking&seed=${seed}&count=20`);
await vpage.waitForSelector(".grid-page[data-ready]");
await vpage.waitForTimeout(3000);
const video = vpage.video();
await recorder.close();
await rename(await video.path(), out + "walking.webm");
await rm(videoDir, { recursive: true, force: true });
console.log("docs/lab/walking.webm");

await browser.close();
await server.close();

if (errors.length) {
  console.error("Ошибки и предупреждения в консоли:\n" + errors.join("\n"));
  process.exit(1);
}
