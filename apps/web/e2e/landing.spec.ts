// T-509: the landing page starts a project from what the visitor typed; public pages fit a phone.
import { expect, test } from "@playwright/test";

import { installMock } from "./mock";
import { fakeSession, signIn } from "./session";

const mock = process.env.E2E_MOCK === "1";

test.describe("landing", () => {
  test.skip(!mock, "only with the API answered by the test");

  test("the text from the landing form becomes the new project", async ({ page }) => {
    await installMock(page);
    await signIn(page, "http://sb.test", fakeSession());
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Техническое задание");
    await expect(page.getByRole("button", { name: "Начать" })).toBeDisabled();
    await page.getByRole("button", { name: "автосервис" }).click();
    await page.getByRole("button", { name: "Начать" }).click();
    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByLabel("Название")).toHaveValue("Автосервис");
    await expect(page.getByLabel(/Бриф/)).toHaveValue(/4 мастера/);
  });

  test("the example ТЗ opens and closes with Escape", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Посмотреть пример готового ТЗ" }).click();
    const dialog = page.getByRole("dialog", { name: "Пример готового ТЗ" });
    await expect(dialog).toContainText("из ответа");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  for (const path of ["/", "/login"]) {
    test(`${path} has no horizontal scroll at 320 px`, async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 640 });
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      const { overflow, offenders } = await page.evaluate(() => {
        const de = document.documentElement;
        const vw = de.clientWidth;
        const offenders = [...document.querySelectorAll("body *")]
          .filter((e) => e.getBoundingClientRect().right > vw + 0.5 && !e.parentElement?.closest(".overflow-hidden"))
          .slice(0, 5)
          .map((e) => `${e.tagName}.${String(e.className).slice(0, 60)}`);
        return { overflow: de.scrollWidth - vw, offenders };
      });
      expect(overflow, offenders.join(" | ")).toBeLessThanOrEqual(0);
    });
  }
});
