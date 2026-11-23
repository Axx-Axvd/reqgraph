// T-512: every screen fits 1440…320 px, survives «break it» attempts, explains its errors, passes axe
// (WCAG 2.1 A and AA) in both themes and keeps still under prefers-reduced-motion. Mock mode only.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { expectNoHorizontalScroll } from "./layout";
import { installMock } from "./mock";
import { installResults, PROJECT } from "./results-mock";
import { fakeSession, signIn } from "./session";

const mock = process.env.E2E_MOCK === "1";
const P = `/projects/${PROJECT}`;
const LONG = "Автосервисобслуживаниеремонттранспортныхсредствлегковыхигрузовыхавтомобилейсдиагностикойишиномонтажомпокраскойкузоваиремонтомдвигателя";

async function setUp(page: Page) {
  await installMock(page);
  await installResults(page);
  await signIn(page, "http://sb.test", fakeSession());
}

/** A project and an interview with the first question asked; returns the interview's address. */
async function interview(page: Page, about = "Автосервис e2e, 4 поста. Клиенты записываются по телефону."): Promise<string> {
  await page.goto("/projects");
  await page.getByRole("button", { name: "Новый проект" }).first().click();
  await page.getByLabel("Чем вы занимаетесь?").fill(about);
  await page.getByRole("button", { name: "Создать проект" }).click();
  await page.getByRole("button", { name: "Начать интервью" }).click();
  await expect(page.locator('[data-role="agent"]').first()).toContainText("Вопрос 1");
  return new URL(page.url()).pathname + new URL(page.url()).search;
}

async function settle(page: Page, path: string) {
  await page.goto(path);
  await page.locator("h1").first().waitFor({ state: "attached" });
  await page.waitForLoadState("networkidle").catch(() => {}); // the interview keeps polling
  await page.waitForTimeout(300);
}

test.describe("quality", () => {
  test.skip(!mock, "only with the API answered by the test");
  test.beforeEach(async ({ page }) => setUp(page));

  for (const width of [1440, 1024, 768, 390, 320]) {
    test(`no horizontal scroll at ${width} px on any screen`, async ({ page }, info) => {
      test.skip(info.project.name !== "desktop", "the widths are set here");
      await page.setViewportSize({ width, height: 900 });
      const talk = await interview(page);
      for (const path of ["/", "/login", "/projects", P, talk, `${P}/graph`, `${P}/graph?view=dev`, `${P}/report`, `${P}/exports`, `${P}/processes/PRC-01`, "/no-such-page"]) {
        await settle(page, path);
        await expectNoHorizontalScroll(page, `${width}px ${path}`);
      }
    });
  }

  for (const theme of ["dark", "light"]) {
    test(`axe finds no A or AA violations in the ${theme} theme`, async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("sg-theme", t), theme);
      const talk = await interview(page);
      for (const path of ["/", "/login", "/projects", P, talk, `${P}/graph`, `${P}/graph?view=dev`, `${P}/report`, `${P}/exports`, `${P}/processes/PRC-01`, "/no-such-page"]) {
        await settle(page, path);
        const { violations } = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const text = violations.map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")}`);
        expect(text, `${theme} ${path}`).toEqual([]);
      }
    });
  }

  test("nothing keeps moving under prefers-reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const path of ["/", "/login", `${P}/report`]) {
      await settle(page, path);
      const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running").length);
      expect(running, path).toBe(0);
    }
  });

  test("an empty or blank answer is not sent, a double click sends once, Ctrl+Enter sends", async ({ page }) => {
    await interview(page);
    const box = page.getByLabel("Ваш ответ");
    const send = page.getByRole("button", { name: "Ответить" });
    await expect(send).toBeDisabled();
    await box.fill("    \n  ");
    await expect(send).toBeDisabled();
    await box.press("Control+Enter");
    await expect(page.locator('[data-role="client"]')).toHaveCount(0);

    let posts = 0;
    page.on("request", (r) => r.url().endsWith("/answer") && r.method() === "POST" && (posts += 1));
    await box.fill("По телефону.");
    await send.dblclick();
    await expect(page.locator('[data-role="client"]')).toHaveCount(1);
    expect(posts).toBe(1);

    await expect(page.locator('[data-role="agent"]').nth(1)).toContainText("Вопрос 2");
    await box.fill("Записи в тетради.");
    await box.press("Control+Enter");
    await expect(page.locator('[data-role="client"]')).toHaveCount(2);
  });

  test("a 130-letter word fits the project, the interview and the phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await interview(page, `${LONG}, 4 поста.`);
    await page.getByLabel("Ваш ответ").fill(LONG);
    await page.getByRole("button", { name: "Ответить" }).click();
    await expect(page.locator('[data-role="client"]')).toContainText(LONG.slice(0, 40));
    await expectNoHorizontalScroll(page, "interview");
    await page.goto("/projects");
    await expect(page.getByText(LONG.slice(0, 30)).first()).toBeVisible();
    await expectNoHorizontalScroll(page, "projects");
  });

  test("dialogs keep Tab inside, close with Escape and give focus back", async ({ page }) => {
    await page.goto("/projects");
    const trigger = page.getByRole("button", { name: "Новый проект" }).first();
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab");
      expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Shift+Tab");
    expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("the theme survives being switched fast", async ({ page }) => {
    await page.goto(P);
    const toggle = page.getByRole("button", { name: /тема$/ });
    const before = await page.locator("html").getAttribute("data-theme");
    for (let i = 0; i < 15; i++) await toggle.click({ delay: 0 });
    const after = await page.locator("html").getAttribute("data-theme");
    expect(after).not.toBe(before);
    expect(await page.evaluate(() => localStorage.getItem("sg-theme"))).toBe(after);
    await expect(toggle).toHaveAccessibleName(after === "light" ? "Тёмная тема" : "Светлая тема");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", after ?? "");
  });

  test("the demo limit says when new runs come and offers the own key", async ({ page }) => {
    await page.route(`http://api.test/projects/${PROJECT}/runs`, (route) =>
      route.request().method() === "POST"
        ? route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ detail: "Лимит демо" }), headers: { "access-control-allow-origin": "*" } })
        : route.fallback(),
    );
    await page.goto(P);
    await page.getByRole("button", { name: "Начать интервью" }).click();
    const problem = page.getByTestId("problem");
    await expect(problem).toContainText("бесплатные прогоны закончились");
    await expect(problem).toContainText("в полночь по Москве");
    await problem.getByRole("button", { name: "Ввести свой ключ" }).click();
    await expect(page.getByRole("dialog", { name: "Свой ключ OpenRouter" })).toBeVisible();
  });

  test("an answer lost on the way stays in the box and goes with «Повторить»", async ({ page }) => {
    await interview(page);
    await page.route("http://api.test/runs/*/answer", (route) => route.abort("internetdisconnected"));
    await page.getByLabel("Ваш ответ").fill("По телефону.");
    await page.getByRole("button", { name: "Ответить" }).click();
    const problem = page.getByTestId("problem");
    await expect(problem).toContainText("Аналитик не получил ответ");
    await expect(page.getByLabel("Ваш ответ")).toHaveValue("По телефону.");
    await page.unroute("http://api.test/runs/*/answer");
    await problem.getByRole("button", { name: "Повторить" }).click();
    await expect(page.locator('[data-role="client"]')).toContainText("По телефону.");
    await expect(problem).toBeHidden();
  });

  test("a wrong address shows a page with the way back", async ({ page }) => {
    await page.goto("/no-such-page");
    await expect(page.getByRole("heading", { name: "Такой страницы нет" })).toBeVisible();
    await expect(page.getByRole("link", { name: "К проектам" })).toBeVisible();
  });
});
