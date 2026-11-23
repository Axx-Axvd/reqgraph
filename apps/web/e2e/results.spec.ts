// T-505 acceptance: a click on a finding highlights its node — on the graph, or the step on the
// BPMN scheme; the exports page gives links to the files.
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { installMock } from "./mock";
import { installResults, PROJECT } from "./results-mock";
import { fakeSession, signIn, type Session } from "./session";

const mock = process.env.E2E_MOCK === "1";
const supabaseUrl = mock ? "http://sb.test" : (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "");

test.describe("mock", () => {
  test.skip(!mock, "only with the API answered by the test");

  test.beforeEach(async ({ page }) => {
    await installMock(page);
    await installResults(page);
    await signIn(page, supabaseUrl, fakeSession());
  });

  test("schemes open as steps in plain words with the client's words", async ({ page }) => {
    await page.goto(`/projects/${PROJECT}/graph`);
    const story = page.getByTestId("process-story");
    await expect(story.getByRole("heading", { name: "Онлайн-запись" })).toBeVisible();
    await expect(story).toContainText("Показать свободные слоты");
    await expect(story).toContainText("со слов: «Хочу, чтобы клиент сам видел свободные окна»");
    await expect(page.locator(".react-flow__node")).toHaveCount(0);
    await expect(page.getByRole("img", { name: "Сценарии использования (UML)" })).toHaveCount(0); // no export yet
    await page.getByRole("link", { name: "Схема для разработчиков" }).click();
    await expect(page.locator('.react-flow__node[data-id="FR-002"]')).toBeVisible();
    await expect(page.getByRole("img", { name: "Мини-карта графа" })).toBeVisible();
  });

  test("checks go one card at a time, and a card shows its node on the graph and on the scheme", async ({ page }, testInfo) => {
    await page.goto(`/projects/${PROJECT}/report`);
    await expect(page.getByTestId("report-summary")).toContainText("Ошибок: 1");
    const card = page.getByTestId("finding");
    await expect(card).toContainText("«Выбор времени»: размытое слово «быстро»"); // errors first, no ids
    await expect(card).not.toContainText("FR-002:");
    await expect(page.getByTestId("ring")).toContainText("Разобрано 0 из 2");

    await card.getByRole("button", { name: "Показать на схеме" }).click();
    await expect(page).toHaveURL(/\/graph\?node=FR-002$/);
    const node = page.locator('.react-flow__node[data-id="FR-002"]');
    await expect(node).toHaveClass(/is-focused/);
    await expect(page.getByRole("complementary", { name: "Узел FR-002" })).toContainText("свободное время");
    await expect(page.locator('.react-flow__node[data-id="TURN-0001"]')).toHaveCount(0); // turns hidden at first
    if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/graph-${testInfo.project.name}.png` });

    await page.goto(`/projects/${PROJECT}/report`);
    await page.getByRole("button", { name: "Понятно, дальше" }).click();
    await expect(page.getByTestId("ring")).toContainText("Разобрано 1 из 2");
    await expect(card).toContainText("«Подтвердить телефон кодом из SMS»: шаг без исполнителя");
    await page.getByRole("button", { name: "Процессы" }).click();
    await expect(card).toContainText("1 из 1");
    await card.getByRole("button", { name: "Показать на схеме" }).click();
    await expect(page).toHaveURL(/\/processes\/PRC-01\?el=PRC-01\.T01$/);
    await expect(page.getByRole("heading", { name: "Онлайн-запись" })).toBeVisible();
    await expect(page.locator('[data-element-id="PRC-01.T01"]').first()).toHaveClass(/is-focused/);
    await page.getByRole("button", { name: "Вписать" }).click();
    if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/bpmn-${testInfo.project.name}.png` });

    await page.goto(`/projects/${PROJECT}/report`);
    await expect(page.getByTestId("ring")).toContainText("Разобрано 1 из 2"); // kept in this browser
  });

  test("documents: the ТЗ sheet tells where an item came from; files by document; a link for the contractor", async ({ page }) => {
    await page.goto(`/projects/${PROJECT}/exports`);
    await expect(page.getByText("Выгрузок пока нет.")).toBeVisible();
    const sheet = page.getByRole("article", { name: "Лист ТЗ" });
    await expect(sheet.getByRole("heading", { name: "Автосервис e2e" })).toBeVisible();
    await sheet.getByRole("button", { name: /Система должна показывать свободное время/ }).click();
    const origin = page.getByTestId("origin");
    await expect(origin).toContainText("«Хочу, чтобы клиент сам видел свободные окна»");
    await expect(origin).toContainText("размытое слово «быстро»");

    await page.getByRole("button", { name: "Сделать документы" }).click();
    await expect(page.getByRole("link", { name: "ТЗ по ГОСТ 34.602 (Word)" })).toHaveAttribute(
      "href",
      new RegExp(`^http://sb\\.test/storage/v1/object/sign/exports/${PROJECT}/1/tz_gost34\\.docx\\?token=t&download=$`),
    );
    await page.getByRole("button", { name: "Ссылка для подрядчика" }).click();
    await expect(page.getByLabel("Ссылка для подрядчика")).toHaveValue(/tz_gost34\.docx\?token=week/);

    await page.getByRole("tab", { name: "SRS" }).click();
    await expect(page.getByRole("link", { name: "SRS по ISO/IEC/IEEE 29148 (Word)" })).toBeVisible();
    await page.getByRole("tab", { name: "SRS" }).press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Схемы" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("export-schemes").getByRole("heading", { name: "Сценарии использования (UML)" })).toBeVisible();
    await page.getByRole("tab", { name: "ReqIF" }).click();
    await expect(page.getByRole("link", { name: "Требования в ReqIF" })).toBeVisible();
  });
});

test.describe("stack", () => {
  test.skip(mock, "only on the running stack");

  test("a run by the brief gives a graph, a report and downloadable exports", async ({ page, request }) => {
    const session: Session = JSON.parse(readFileSync(join(__dirname, ".session.json"), "utf-8"));
    await signIn(page, supabaseUrl, session);
    await page.goto("/projects");
    await page.getByRole("button", { name: "Новый проект" }).first().click();
    await page.getByLabel("Чем вы занимаетесь?").fill("Результаты e2e, автосервис, 4 поста. Клиенты записываются по телефону.");
    await page.getByRole("button", { name: "Создать проект" }).click();
    await expect(page.getByRole("heading", { name: "Результаты e2e" })).toBeVisible();
    const projectUrl = page.url();
    await page.getByRole("button", { name: "Прогон по брифу" }).click();
    await expect(page.getByTestId("run-status")).toContainText("завершён", { timeout: 120_000 });

    await page.goto(`${projectUrl}/graph?view=dev`);
    await expect(page.locator(".react-flow__node").first()).toBeVisible();

    await page.goto(`${projectUrl}/report`);
    await expect(page.getByTestId("report-summary")).toContainText("проверок:");
    const show = page.getByTestId("finding").getByRole("button", { name: "Показать на схеме" });
    if ((await show.count()) > 0) {
      await show.click();
      await expect(page.locator(".is-focused").first()).toBeVisible();
    }

    await page.goto(`${projectUrl}/exports`);
    await page.getByRole("button", { name: "Сделать документы" }).click();
    await expect(page.getByRole("link", { name: "ТЗ по ГОСТ 34.602 (Word)" })).toBeVisible({ timeout: 120_000 });
    await page.getByRole("tab", { name: "ReqIF" }).click();
    const link = page.getByRole("link", { name: "Требования в ReqIF" });
    await expect(link).toBeVisible({ timeout: 120_000 });
    const response = await request.get((await link.getAttribute("href")) ?? "");
    expect(response.status()).toBe(200);
  });
});
