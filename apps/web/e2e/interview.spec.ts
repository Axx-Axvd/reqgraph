// T-504 acceptance: sign in, create a project, start an interview and answer 3 questions;
// the questions appear without reloading the page (Realtime or the polling fallback).
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { installMock } from "./mock";
import { fakeSession, signIn, type Session } from "./session";

const mock = process.env.E2E_MOCK === "1";
const supabaseUrl = mock ? "http://sb.test" : (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "");

test("create a project and answer 3 interview questions", async ({ page }, testInfo) => {
  if (mock) await installMock(page);
  const session: Session = mock
    ? fakeSession()
    : JSON.parse(readFileSync(join(__dirname, ".session.json"), "utf-8"));
  await signIn(page, supabaseUrl, session);

  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  await expect(page.getByTestId("usage")).toContainText("осталось прогонов сегодня");
  await page.getByLabel("Название").fill("Стоматология e2e");
  await page.getByLabel(/Бриф/).fill("Стоматологическая клиника, 3 кресла. Пациенты записываются по телефону.");
  await page.getByRole("button", { name: "Создать" }).click();

  await expect(page.getByRole("heading", { name: "Стоматология e2e" })).toBeVisible();
  await page.getByRole("button", { name: "Начать интервью" }).click();
  await expect(page.getByRole("heading", { name: "Интервью" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("Не вводите персональные данные");

  for (let n = 1; n <= 3; n++) {
    await expect(page.locator('[data-role="agent"]').nth(n - 1)).toContainText(`Вопрос ${n}`, { timeout: 60_000 });
    await page.getByLabel("Ваш ответ").fill(`Ответ ${n}: по телефону, записи в тетради.`);
    await page.getByRole("button", { name: "Ответить" }).click();
    await expect(page.locator('[data-role="client"]').nth(n - 1)).toContainText(`Ответ ${n}`);
  }
  await expect(page.locator('[data-role="agent"]').nth(3)).toContainText("Вопрос 4", { timeout: 60_000 });
  if (process.env.E2E_SHOTS) {
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/chat-${testInfo.project.name}.png`, fullPage: true });
  }
  await page.getByRole("button", { name: /Готово/ }).click();
  await expect(page.getByTestId("run-status")).toContainText("завершён", { timeout: 90_000 });
  expect(await page.evaluate(() => Object.keys(window.localStorage).join(","))).not.toContain("openrouter");
});

test("the level is chosen before the interview and «проще» asks the question again", async ({ page }) => {
  if (mock) await installMock(page);
  const session: Session = mock
    ? fakeSession()
    : JSON.parse(readFileSync(join(__dirname, ".session.json"), "utf-8"));
  await signIn(page, supabaseUrl, session);

  await page.goto("/projects");
  await page.getByLabel("Название").fill("Уровень e2e");
  await page.getByLabel(/Бриф/).fill("Автосервис, 2 подъёмника. Клиенты звонят мастеру.");
  await page.getByRole("button", { name: "Создать" }).click();
  await expect(page.getByRole("heading", { name: "Уровень e2e" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Простыми словами/ })).toBeChecked(); // the default
  await page.getByRole("radio", { name: /Немного разбираюсь/ }).check();
  const started = page.waitForRequest((r) => r.method() === "POST" && /\/projects\/[^/]+\/runs$/.test(r.url()));
  await page.getByRole("button", { name: "Начать интервью" }).click();
  expect((await started).postDataJSON()).toMatchObject({ kind: "interview", client_level: 1 });

  const agent = page.locator('[data-role="agent"]');
  await expect(agent.first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Слишком сложно — проще" }).click();
  await expect(page.locator('[data-role="client"]').first()).toContainText("Слишком сложно");
  await expect(agent).toHaveCount(2, { timeout: 60_000 });
  await expect(page.getByLabel("Ваш ответ")).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /Готово/ }).click();
  await expect(page.getByTestId("run-status")).toContainText("завершён", { timeout: 90_000 });
});
