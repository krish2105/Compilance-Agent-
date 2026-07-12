import { defineConfig, devices } from "@playwright/test";

/**
 * E2E harness: spins up the real backend (uvicorn, offline LLM) + the built
 * frontend (pointed at that backend), then drives full user journeys in Chromium
 * — desktop and mobile viewports.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Pixel 5 is Chromium-based (no extra WebKit download needed).
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
  webServer: [
    {
      // Backend API (deterministic offline mode).
      command:
        "bash -c 'cd ../backend && (.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8099 || python -m uvicorn app.main:app --host 127.0.0.1 --port 8099)'",
      env: { LLM_PROVIDER: "offline", BACKEND_API_KEY: "dev-local-key", CORS_ORIGINS: "*" },
      url: "http://127.0.0.1:8099/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      // Frontend served by vite preview. Pre-build with `npm run build:e2e` (CI does
      // this before invoking playwright); locally reuses a running preview if present.
      command: "npm run preview -- --port 4173 --strictPort --host 127.0.0.1",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
