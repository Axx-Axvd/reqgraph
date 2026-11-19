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

  test("a click on a finding highlights the node on the graph and the step on the scheme", async ({ page }, testInfo) => {
    await page.goto(`/projects/${PROJECT}/report`);
    await expect(page.getByTestId("report-summary")).toContainText("Ошибок: 1");

    await page.getByTestId("finding").filter({ hasText: "FR-002" }).click();
    await expect(page).toHaveURL(/\/graph\?node=FR-002$/);
    const node = page.locator('.react-flow__node[data-id="FR-002"]');
    await expect(node).toHaveClass(/is-focused/);
    await expect(page.getByRole("complementary", { name: "Узел FR-002" })).toContainText("свободное время");
    await expect(page.locator('.react-flow__node[data-id="TURN-0001"]')).toHaveCount(0); // turns hidden at first
    if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/graph-${testInfo.project.name}.png` });

    await page.goto(`/projects/${PROJECT}/report`);
    await page.getByTestId("finding").filter({ hasText: "PRC-01.T01" }).click();
    await expect(page).toHaveURL(/\/processes\/PRC-01\?el=PRC-01\.T01$/);
    await expect(page.locator('[data-element-id="PRC-01.T01"]').first()).toHaveClass(/is-focused/);
    if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/bpmn-${testInfo.project.name}.png` });
  });

  test("the exports page makes the documents and links them", async ({ page }) => {
    await page.goto(`/projects/${PROJECT}/exports`);
    await expect(page.getByText("Выгрузок пока нет.")).toBeVisible();
    await page.getByRole("button", { name: "Сделать документы" }).click();
    const link = page.getByRole("link", { name: "SRS по ISO/IEC/IEEE 29148 (Word)" });
    await expect(link).toHaveAttribute("href", new RegExp(`^http://sb\\.test/storage/v1/object/sign/exports/${PROJECT}/1/srs\\.docx`));
    await expect(page.getByRole("link", { name: "Требования в ReqIF" })).toBeVisible();
  });
});

test.describe("stack", () => {
  test.skip(mock, "only on the running stack");

  test("a run by the brief gives a graph, a report and downloadable exports", async ({ page, request }) => {
    const session: Session = JSON.parse(readFileSync(join(__dirname, ".session.json"), "utf-8"));
    await signIn(page, supabaseUrl, session);
    await page.goto("/projects");
    await page.getByLabel("Название").fill("Результаты e2e");
    await page.getByLabel(/Бриф/).fill("Автосервис, 4 поста. Клиенты записываются по телефону.");
    await page.getByRole("button", { name: "Создать" }).click();
    await expect(page.getByRole("heading", { name: "Результаты e2e" })).toBeVisible();
    const projectUrl = page.url();
    await page.getByRole("button", { name: "Прогон по брифу" }).click();
    await expect(page.getByTestId("run-status")).toContainText("завершён", { timeout: 120_000 });

    await page.goto(`${projectUrl}/graph`);
    await expect(page.locator(".react-flow__node").first()).toBeVisible();

    await page.goto(`${projectUrl}/report`);
    await expect(page.getByTestId("report-summary")).toContainText("проверок:");
    const withNode = page.getByTestId("finding").and(page.locator(":not([disabled])"));
    if ((await withNode.count()) > 0) {
      await withNode.first().click();
      await expect(page.locator(".is-focused").first()).toBeVisible();
    }

    await page.goto(`${projectUrl}/exports`);
    await page.getByRole("button", { name: "Сделать документы" }).click();
    const link = page.getByRole("link", { name: "Требования в ReqIF" });
    await expect(link).toBeVisible({ timeout: 120_000 });
    const response = await request.get((await link.getAttribute("href")) ?? "");
    expect(response.status()).toBe(200);
  });
});
