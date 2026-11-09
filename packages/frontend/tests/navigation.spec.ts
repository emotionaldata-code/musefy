import { expect, test, type Page } from "@playwright/test";
import { account } from "./account";
import title from "./title.json" with { type: "json" };

const listId = "ccf05672-08d5-4a27-a72d-b0b0f418db15";

async function mockNavigation(page: Page) {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: account });
    if (url.pathname.endsWith("/facets"))
      return route.fulfill({ json: { counts: {}, years: [], genres: [] } });
    if (url.pathname.endsWith("/titles/1")) return route.fulfill({ json: title });
    if (url.pathname.endsWith(`/lists/${listId}`))
      return route.fulfill({ status: 404, json: {} });
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 20 } });
  });
}

async function navigate(page: Page, name: string, mobile: boolean) {
  if (mobile) await page.getByRole("button", { name: "Apri menu", exact: true }).click();
  await page.getByRole("navigation").getByRole("button", { name, exact: true }).click();
}

for (const width of [1440, 390, 320]) {
  test(`navigation separates formats from community at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockNavigation(page);
    await page.goto("/");
    await navigate(page, "Esplora", width <= 1000);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Esplora");
    const formats = page.getByRole("group", { name: "Formato nel catalogo" });
    await expect(formats.getByRole("button")).toHaveText(["Tutti", "Film", "Serie TV", "Anime", "Manga"]);
    for (const [label, value] of [["Film", "movie"], ["Serie TV", "tv"], ["Anime", "anime"], ["Manga", "manga"], ["Tutti", ""]]) {
      await formats.getByRole("button", { name: label, exact: true }).click();
      await expect(formats.locator('[aria-pressed="true"]')).toHaveText(label);
      await expect.poll(() => new URL(page.url()).searchParams.get("source_type") ?? "").toBe(value);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const rowPositions = await formats.getByRole("button").evaluateAll((buttons) => buttons.map((button) => Math.round(button.getBoundingClientRect().top)));
    expect(new Set(rowPositions).size).toBe(1);
    await page.screenshot({ path: `/tmp/musefy-navigation-${width}.png`, fullPage: true });
    await navigate(page, "Le tue liste", width <= 1000);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Le tue liste");
    await expect(formats).toHaveCount(0);
    await expect(page.getByRole("search", { name: "Cerca nel catalogo" })).toHaveCount(0);
    await navigate(page, "Scopri liste", width <= 1000);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Scopri liste");
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Le tue liste");
    await page.goForward();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Scopri liste");
    await navigate(page, "Musefy", width <= 1000);
    await expect(page.getByRole("heading", { name: "Cosa vuoi farti consigliare?" })).toBeVisible();
  });
}

test("shared list routes survive reload, title details and browser history", async ({ page }) => {
  await mockNavigation(page);
  const destination = `/?view=lists&list=${listId}&share=private-link-token`;
  await page.goto(destination);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Le tue liste");
  await expect(page).toHaveURL(destination);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Le tue liste");
  await expect(page).toHaveURL(destination);
  await page.evaluate(() => { window.location.hash = "title/1"; });
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page).toHaveURL(destination);
  await navigate(page, "Esplora", false);
  await expect(page).toHaveURL(/\?view=catalog$/);
  await page.goBack();
  await expect(page).toHaveURL(destination);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Le tue liste");
});

test("login preserves the shared list destination", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ status: 401, json: {} }));
  const destination = `/?view=discover&list=${listId}&share=private-link-token#title/1`;
  await page.goto(destination);
  const link = page.getByRole("link", { name: "Continua con Google" });
  const href = await link.getAttribute("href");
  expect(new URL(href!, page.url()).searchParams.get("return_to")).toBe(destination);
  await expect(page).toHaveURL(destination);
});
