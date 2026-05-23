// Render SVG snapshots to PNG and capture a dashboard screenshot.
// Run: bun /tmp/lattice_screenshots.ts

import { readdirSync, readFileSync } from "node:fs";
import { stat } from "node:fs/promises";
import { chromium } from "playwright";

const SRC = "/tmp/lattice_screenshots";
const PNG_OUT = "/tmp/lattice_screenshots/png";
const DASH = "http://127.0.0.1:8765";

async function main() {
  // ensure png dir
  await Bun.$`mkdir -p ${PNG_OUT}`.quiet();

  const browser = await chromium.launch();

  // 1. Convert every .svg in SRC to a .png in PNG_OUT
  const svgs = readdirSync(SRC).filter((f) => f.endsWith(".svg"));
  for (const svgName of svgs) {
    const svg = readFileSync(`${SRC}/${svgName}`, "utf8");
    const html = `<!doctype html><html><head><meta charset="utf-8">
      <style>
        html, body { margin: 0; padding: 24px; background: #0b0b0d; }
        svg { display: block; width: auto; height: auto; max-width: 100%; }
      </style></head><body>${svg}</body></html>`;
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.setContent(html, { waitUntil: "domcontentloaded", timeout: 10000 });
    await page.waitForTimeout(300);
    // Let the SVG layout settle, then size the viewport to the SVG box
    const box = await page.evaluate(() => {
      const svg = document.querySelector("svg") as SVGSVGElement | null;
      if (!svg) return null;
      const r = svg.getBoundingClientRect();
      return { w: Math.ceil(r.width) + 48, h: Math.ceil(r.height) + 48 };
    });
    if (box) {
      await page.setViewportSize({ width: Math.max(800, box.w), height: Math.max(400, box.h) });
    }
    const outPath = `${PNG_OUT}/${svgName.replace(/\.svg$/, ".png")}`;
    await page.screenshot({ path: outPath, fullPage: false, omitBackground: false });
    await page.close();
    const s = await stat(outPath);
    console.log(`OK ${outPath}  (${Math.round(s.size / 1024)} KB)`);
  }

  // 2. Dashboard screenshots
  // - landing (claim DAG)
  // - stats panel (scrolled if needed)
  const dashPage = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  await dashPage.goto(DASH, { waitUntil: "networkidle" });
  // Give D3 time to render
  await dashPage.waitForTimeout(2500);
  await dashPage.screenshot({ path: `${PNG_OUT}/06_dashboard.png`, fullPage: false });
  console.log(`OK ${PNG_OUT}/06_dashboard.png`);

  // 3. Full-page dashboard for context
  await dashPage.screenshot({ path: `${PNG_OUT}/07_dashboard_fullpage.png`, fullPage: true });
  console.log(`OK ${PNG_OUT}/07_dashboard_fullpage.png`);

  await dashPage.close();
  await browser.close();
}

main().catch((err) => { console.error(err); process.exit(1); });
