import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against a LOCAL stack only (never production):
 *   backend  http://127.0.0.1:8000   (uvicorn, migrated + seeded DB: `python -m scripts.seed_master_data && python -m scripts.seed_users`)
 *   frontend http://localhost:5173   (vite dev server, VITE_API_BASE_URL -> the backend above)
 *
 * The specs share one database and one procurement "cycle", so they run serially in file order.
 */
export const BASE_URL = process.env.QA_BASE_URL ?? "http://localhost:5173";
export const API_URL = process.env.QA_API_URL ?? "http://127.0.0.1:8000/api/v1";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["json", { outputFile: "results/results.json" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
