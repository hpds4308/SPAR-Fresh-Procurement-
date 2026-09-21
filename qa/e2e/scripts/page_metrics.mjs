// Page-load metrics for the PRODUCTION build (vite build -> vite preview), unthrottled and on "Slow 4G".
// Usage:  node scripts/page_metrics.mjs [baseUrl=http://localhost:4173] [apiUrl=http://127.0.0.1:8000/api/v1]
// Local only. Numbers are indicative (single run per profile on a dev laptop), not a Lighthouse score.
import { chromium } from "@playwright/test";

const BASE = process.argv[2] ?? "http://localhost:4173";
const API = process.argv[3] ?? "http://127.0.0.1:8000/api/v1";
if (!/localhost|127\.0\.0\.1/.test(BASE + API)) throw new Error("local only");

const PROFILES = {
  "no throttling": null,
  "Slow 4G (1.6 Mbps, 150 ms RTT)": { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 },
  "Fast 3G (0.75 Mbps, 300 ms RTT)": { offline: false, latency: 300, downloadThroughput: (0.75 * 1024 * 1024) / 8, uploadThroughput: (250 * 1024) / 8 },
};

async function measure(browser, name, net, path, session) {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 667 }, deviceScaleFactor: 2 });
  if (session) await ctx.addInitScript(([a, r]) => { localStorage.setItem("spar_access_token", a); localStorage.setItem("spar_refresh_token", r); sessionStorage.removeItem("spar_welcome_pending"); }, session);
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  if (net) await cdp.send("Network.emulateNetworkConditions", net);
  const sizes = new Map(); const kinds = new Map(); let requests = 0;
  cdp.on("Network.responseReceived", (e) => { requests++; kinds.set(e.requestId, e.type + " " + new URL(e.response.url).pathname); });
  cdp.on("Network.loadingFinished", (e) => sizes.set(e.requestId, e.encodedDataLength));
  await page.addInitScript(() => {
    window.__m = {};
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
  });
  const t0 = Date.now();
  await page.goto(BASE + path, { waitUntil: "commit" });
  const ready = path === "/login" ? page.getByRole("button", { name: "Sign in" }) : page.locator("main").getByText(/Ordering today|Order submitted successfully|Ordering for .* is closed|closed/).first();
  await ready.waitFor({ timeout: 120000 });
  const interactive = Date.now() - t0;
  await page.waitForTimeout(1500);
  const m = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    const fcp = performance.getEntriesByName("first-contentful-paint")[0]?.startTime;
    return { fcp, lcp: window.__m.lcp, dcl: nav.domContentLoadedEventEnd, load: nav.loadEventEnd };
  });
  let total = 0, video = 0, api = 0;
  for (const [id, bytes] of sizes) { total += bytes; const k = kinds.get(id) ?? ""; if (k.includes(".mp4")) video += bytes; if (k.includes("/api/v1/")) api++; }
  await ctx.close();
  return { name, path, "content visible (ms)": interactive, "FCP (ms)": Math.round(m.fcp), "LCP (ms)": Math.round(m.lcp), "load event (ms)": Math.round(m.load), "requests": requests, "API calls": api, "transferred (KB)": Math.round(total / 1024), "of which video (KB)": Math.round(video / 1024) };
}

const browser = await chromium.launch();
const rows = [];
const login = await (await fetch(API + "/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "br05", password: process.env.QA_PASSWORD ?? "ChangeMe123!" }) })).json();
for (const [name, net] of Object.entries(PROFILES)) {
  rows.push(await measure(browser, name, net, "/login", null));
  rows.push(await measure(browser, name, net, "/branch", [login.access_token, login.refresh_token]));
}
await browser.close();
console.table(rows);
