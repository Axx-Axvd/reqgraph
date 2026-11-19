// End-to-end tests of the web app (T-504). Two modes, one scenario:
// - E2E_MOCK=1: the API and Supabase are answered by the test itself (page.route), no services;
// - otherwise: a running stack — local Supabase (supabase start), the API with the worker on stub
//   models (REQGRAPH_STUB_MODELS=1) — as the CI job «e2e» runs it.
import { defineConfig, devices, type PlaywrightTestConfig } from "@playwright/test";

const mockEnv = {
  NEXT_PUBLIC_SUPABASE_URL: "http://sb.test",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "anon-test-key",
  NEXT_PUBLIC_API_URL: "http://api.test",
  NEXT_TELEMETRY_DISABLED: "1",
};

export function configFor(mock: boolean): PlaywrightTestConfig {
  if (mock) process.env.E2E_MOCK = "1"; // read by the spec in the test workers
  const port = Number(process.env.E2E_PORT ?? (mock ? 3100 : 3000));
  return defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  globalSetup: mock ? undefined : "./e2e/global-setup.ts",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "off",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `pnpm build && pnpm start -p ${port}`,
    url: `http://127.0.0.1:${port}`,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    env: mock ? { ...process.env, ...mockEnv } as Record<string, string> : (process.env as Record<string, string>),
  },
});
}

export default configFor(process.env.E2E_MOCK === "1");
