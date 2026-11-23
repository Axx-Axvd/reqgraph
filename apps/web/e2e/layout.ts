// Layout helpers of the e2e tests (T-509, T-512).
import { expect, type Page } from "@playwright/test";

/** The page is not wider than the window; the message names the first elements that stick out. */
export async function expectNoHorizontalScroll(page: Page, label = ""): Promise<void> {
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
  expect(overflow, `${label} ${offenders.join(" | ")}`).toBeLessThanOrEqual(0);
}
