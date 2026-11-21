// T-506: the smoke test against the deployed demo (smoke.yml); nothing is built or started here.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "smoke.spec.ts",
  timeout: 120_000,
  expect: { timeout: 60_000 }, // Render wakes up in up to a minute
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.SMOKE_WEB_URL,
    trace: "off",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }],
});
