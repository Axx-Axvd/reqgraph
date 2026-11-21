// T-506 smoke: the public demo is up. The same test runs against prod (smoke.yml, SMOKE_WEB_URL and
// SMOKE_API_URL), against the local stack in CI (e2e) and with mocks here (e2e:mock).
// The API is called from the site's page, so the browser also checks CORS for the site's origin.
import { expect, test } from "@playwright/test";

const mock = process.env.E2E_MOCK === "1";
const api = process.env.SMOKE_API_URL ?? (mock ? "http://api.test" : process.env.NEXT_PUBLIC_API_URL ?? "");

test("smoke: sign-in page, API health, no data without sign-in, GitHub sign-in", async ({ page }, testInfo) => {
  if (mock) {
    const cors = { "access-control-allow-origin": "*" };
    await page.route("http://api.test/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/health") {
        return route.fulfill({ json: { status: "ok", database: true, memory_mb: 180, peak_memory_mb: 240 }, headers: cors });
      }
      return route.fulfill({ status: 401, json: { detail: "нужен вход" }, headers: cors });
    });
    await page.route("http://sb.test/auth/v1/authorize**", (route) => route.fulfill({ body: "github" }));
  }

  await page.goto("/login");
  await expect(page.getByRole("note")).toContainText("Не вводите персональные данные");

  const health = await page.evaluate(async (url) => (await fetch(`${url}/health`)).json(), api);
  expect(health.status).toBe("ok");
  expect(health.database).toBe(true);
  testInfo.annotations.push({ type: "memory", description: `${health.memory_mb} MB, peak ${health.peak_memory_mb} MB` });
  console.log(`API memory: ${health.memory_mb} MB, peak ${health.peak_memory_mb} MB`);

  const status = await page.evaluate(async (url) => (await fetch(`${url}/projects`)).status, api);
  expect(status).toBe(401);

  const authorize = page.waitForRequest(/\/auth\/v1\/authorize\?provider=github/);
  await page.getByRole("button", { name: "Войти через GitHub" }).click();
  await authorize;
});
