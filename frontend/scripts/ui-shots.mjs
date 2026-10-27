// Кадры раскладки игры на разных экранах (2560×1440 … 375×667): вступление, разговор, карта, лист героя.
// Нужен запущенный `npm run dev`. Кадры — в docs/play/ui-*.png (или в каталог из аргумента).
import { chromium } from "playwright";
const out = process.argv[2] ?? new URL("../../docs/play", import.meta.url).pathname;
const b = await chromium.launch();
for (const [w, h] of [[2560, 1440], [1920, 1080], [1280, 720], [375, 667]]) {
  const p = await b.newPage({ viewport: { width: w, height: h } });
  const errs = [];
  p.on("console", (m) => (m.type() === "error" || m.type() === "warning") && errs.push(m.text()));
  await p.goto("http://localhost:5173/play/demo?seed=1");
  await p.evaluate(() => localStorage.clear());
  await p.reload();
  await p.getByRole("button", { name: "Начать" }).click();
  await p.waitForSelector(".dlg:not(.hidden)");
  await p.waitForTimeout(900);
  await p.screenshot({ path: `${out}/ui-${w}-dialog.png` });
  for (let i = 0; i < 20 && (await p.locator(".dlg:not(.hidden)").isVisible()); i++) {
    const next = p.getByRole("button", { name: "Далее ▸" });
    if (await next.isVisible()) await next.click(); else await p.locator(".dlg .choice:not(.locked)").first().click();
    await p.waitForTimeout(80);
  }
  await p.waitForTimeout(900);
  await p.screenshot({ path: `${out}/ui-${w}-map.png` });
  for (let i = 0; i < 10 && !(await p.locator(".dlg:not(.hidden)").isVisible()); i++) {
    const pos = await p.evaluate(() => window.__rpg.scene.screenPos("marfa_at_stall"));
    await p.mouse.click(Math.min(w - 10, Math.max(10, pos.x)), Math.min(h - 10, Math.max(80, pos.y)));
    await p.waitForTimeout(1200);
  }
  for (let i = 0; i < 6 && (await p.getByRole("button", { name: "Далее ▸" }).isVisible()); i++) {
    await p.getByRole("button", { name: "Далее ▸" }).click();
    await p.waitForTimeout(100);
  }
  await p.waitForTimeout(900);
  await p.screenshot({ path: `${out}/ui-${w}-talk.png` });
  for (let i = 0; i < 30 && (await p.locator(".dlg:not(.hidden)").isVisible()); i++) {
    const next = p.getByRole("button", { name: "Далее ▸" });
    if (await next.isVisible()) await next.click(); else await p.locator(".dlg .choice:not(.locked)").last().click();
    await p.waitForTimeout(80);
  }
  await p.waitForTimeout(300);
  if (await p.locator(".sheet:not(.hidden)").isVisible()) await p.locator(".sheet-close").click();
  await p.getByRole("button", { name: /Герой/ }).click();
  await p.waitForTimeout(300);
  await p.screenshot({ path: `${out}/ui-${w}-sheet.png` });
  console.log(w, errs.join(" | ") || "ok");
  await p.close();
}
await b.close();
