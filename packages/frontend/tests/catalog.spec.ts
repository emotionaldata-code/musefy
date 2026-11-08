import { expect, test } from "@playwright/test";
import fixture from "./title.json" with { type: "json" };

// Mock every API request; tests never contact metadata providers.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/facets")) {
      await route.fulfill({
        json: { counts: { movie: 31 }, years: [2020], genres: ["Drama"] },
      });
    } else if (url.pathname.endsWith("/titles/1")) {
      await route.fulfill({ json: fixture });
    } else {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const empty = url.searchParams.get("q") === "inesistente";
      const filtered = url.searchParams.get("source_type") === "manga";
      const items =
        empty || filtered
          ? []
          : Array.from({ length: Math.min(15, 31 - offset) }, (_, index) => ({
              ...fixture,
              id: offset + index + 1,
              title:
                offset + index === 0
                  ? fixture.title
                  : `Titolo ${offset + index + 1}`,
            }));
      await route.fulfill({
        json: { items, offset, total: empty || filtered ? 0 : 31, limit: 15 },
      });
    }
  });
});

test("browse continuously, search, details and empty results", async ({
  page,
}) => {
  await page.goto("/?view=catalog");
  await expect(page.getByText("31 titoli", { exact: true })).toBeVisible();
  await expect(page.locator(".title-card")).toHaveCount(15);
  await page
    .getByRole("link", { name: "Apri Titolo 15", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("link", { name: "Apri Titolo 30", exact: true }),
  ).toBeAttached();
  await page
    .getByRole("link", { name: "Apri Titolo 30", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(page.locator(".title-card")).toHaveCount(31);
  await expect(page.getByText("31 titoli visualizzati")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Pagina successiva|Pagina precedente/ }),
  ).toHaveCount(0);
  await expect(page).not.toHaveURL(/offset=/);
  await page
    .getByRole("textbox", { name: "Cerca un titolo" })
    .scrollIntoViewIfNeeded();
  await page.getByRole("textbox", { name: "Cerca un titolo" }).fill("storia");
  await expect(page).toHaveURL(/q=storia/);
  await expect(page).not.toHaveURL(/offset=15/);
  await page.getByRole("link", { name: "Apri Una storia" }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("heading", { name: "Sinossi", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page
    .getByRole("textbox", { name: "Cerca un titolo" })
    .fill("inesistente");
  await expect(
    page.getByRole("heading", { name: "Nessun titolo trovato" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rimuovi filtri" }).click();
  await expect(page.getByText("31 titoli", { exact: true })).toBeVisible();
});

test("phone category filters, API error and retry", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=catalog");
  await page.getByRole("button", { name: "Apri menu", exact: true }).click();
  await page.getByRole("button", { name: "Manga 0" }).click();
  await expect(page).toHaveURL(/source_type=manga/);
  await expect(
    page.getByRole("heading", { name: "Nessun titolo trovato" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.route("**/api/titles?**", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page.getByRole("button", { name: "Aggiorna catalogo" }).click();
  await expect(page.getByRole("alert")).toContainText("HTTP 503");
  await page.unroute("**/api/titles?**");
  await page.getByRole("button", { name: "Riprova" }).click();
  await expect(
    page.getByRole("heading", { name: "Nessun titolo trovato" }),
  ).toBeVisible();
});

for (const width of [1440, 390]) {
  test(`source, year and genre menus at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/?offset=15");
    const source = page.getByRole("combobox", { name: "Fonte", exact: true });
    await source.focus();
    await page.keyboard.press("Space");
    await page.getByRole("option", { name: "TMDB", exact: true }).click();
    await expect(page).toHaveURL(/source=tmdb/);
    await expect(page).not.toHaveURL(/offset=15/);
    await expect(source).toBeFocused();

    await page.getByRole("combobox", { name: "Anno", exact: true }).click();
    await page.getByRole("option", { name: "2020", exact: true }).click();
    await expect(page).toHaveURL(/year=2020/);
    await page.getByRole("combobox", { name: "Genere", exact: true }).click();
    await page.getByRole("option", { name: "Drama", exact: true }).click();
    await expect(page).toHaveURL(/genre=Drama/);
    await page.getByRole("combobox", { name: "Fonte", exact: true }).click();
    await page
      .getByRole("option", { name: "Tutte le fonti", exact: true })
      .click();
    await expect(page).not.toHaveURL(/source=tmdb/);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Rimuovi filtri" }).click();
    await expect(
      page.getByRole("combobox", { name: "Genere", exact: true }),
    ).toHaveText("Genere");
  });
}

test("long details scroll independently, remain keyboard accessible and close on phones", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/titles/1", (route) =>
    route.fulfill({
      json: {
        ...fixture,
        metadata: {
          ...fixture.metadata,
          synopsis: "Una lunga sinossi per verificare lo scorrimento. ".repeat(
            100,
          ),
          cast: Array.from({ length: 60 }, (_, index) => ({
            name: `Interprete ${index}`,
            source_id: index,
            role: "Actor",
            character: "Personaggio",
            language: null,
          })),
        },
      },
    }),
  );
  await page.goto("/#title/1");
  const content = page.getByRole("region", {
    name: "Contenuto della scheda",
    exact: true,
  });
  const cast = page.getByRole("region", {
    name: "Cast e personaggi",
    exact: true,
  });
  await page.getByText("Cast e autori", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Cast e personaggi", exact: true }),
  ).toBeVisible();
  await content.focus();
  await page.keyboard.press("PageDown");
  await expect
    .poll(() => content.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await cast.scrollIntoViewIfNeeded();
  const outerTop = await content.evaluate((element) => element.scrollTop);
  await cast.focus();
  await page.keyboard.press("PageDown");
  await expect
    .poll(() => cast.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  expect(await content.evaluate((element) => element.scrollTop)).toBe(outerTop);
  expect(
    await page
      .getByRole("dialog")
      .evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Chiudi scheda", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
});

test("next-page errors keep cards and retry the same offset once", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/api/titles?**", async (route) => {
    const offset = Number(
      new URL(route.request().url()).searchParams.get("offset"),
    );
    if (offset !== 15) return route.fallback();
    requests += 1;
    if (requests === 1) return route.fulfill({ status: 503, json: {} });
    return route.fulfill({
      json: {
        items: [{ ...fixture, id: 16, title: "Ultimo titolo" }],
        total: 16,
        offset: 15,
        limit: 15,
      },
    });
  });
  await page.goto("/?view=catalog");
  await page
    .getByRole("link", { name: "Apri Titolo 15", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(page.getByRole("alert")).toContainText("HTTP 503");
  await expect(page.locator(".title-card")).toHaveCount(15);
  expect(requests).toBe(1);
  await page.getByRole("button", { name: "Riprova", exact: true }).click();
  await expect(page.locator(".title-card")).toHaveCount(16);
  await expect(page.getByText("16 titoli visualizzati")).toBeVisible();
  expect(requests).toBe(2);
});

test("a late page cannot contaminate a new category", async ({ page }) => {
  let release: () => void = () => {};
  let requested = false;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/titles?**", async (route) => {
    if (new URL(route.request().url()).searchParams.get("offset") !== "15")
      return route.fallback();
    requested = true;
    await pending;
    await route.fulfill({
      json: {
        items: [{ ...fixture, id: 16, title: "Risposta vecchia" }],
        total: 16,
        offset: 15,
        limit: 15,
      },
    });
  });
  await page.goto("/?view=catalog");
  await page
    .getByRole("link", { name: "Apri Titolo 15", exact: true })
    .scrollIntoViewIfNeeded();
  await expect.poll(() => requested).toBe(true);
  await page.getByRole("button", { name: "Manga 0", exact: true }).click();
  release();
  await expect(
    page.getByRole("heading", { name: "Nessun titolo trovato" }),
  ).toBeVisible();
  await expect(page.locator(".title-card")).toHaveCount(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

for (const width of [1440, 390]) {
  test(`system theme, manual toggle and persistence at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await page.goto("/?view=catalog");
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveClass(/dark/);
    await page.getByRole("button", { name: "Attiva tema chiaro" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.reload();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.getByRole("button", { name: "Attiva tema scuro" }).click();
    await page.reload();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await page
      .getByRole("link", { name: "Apri Una storia", exact: true })
      .click();
    await expect(
      page.getByRole("dialog").getByText("TMDB · 10 voti", { exact: true }),
    ).not.toBeVisible();
    await page.getByText("Altri dettagli", { exact: true }).click();
    await expect(
      page.getByRole("dialog").getByText("TMDB · 10 voti", { exact: true }),
    ).toBeVisible();
    expect(
      await page
        .getByRole("dialog")
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBe(true);
  });
}

for (const width of [1440, 390]) {
  test(`filters keep the catalog width stable at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/?view=catalog");
    await expect(page.locator(".title-card").first()).toBeVisible();
    const frame = () =>
      page.locator("main").evaluate((element) => {
        const { x, width } = element.getBoundingClientRect();
        return { x, width };
      });
    const before = await frame();
    for (const name of ["Fonte", "Anno", "Genere"]) {
      await page.getByRole("combobox", { name, exact: true }).click();
      await expect(page.locator("body")).toHaveAttribute(
        "data-scroll-locked",
        /\d/,
      );
      expect(await frame()).toEqual(before);
      await page.keyboard.press("Escape");
      await expect(page.locator("body")).not.toHaveAttribute(
        "data-scroll-locked",
      );
      expect(await frame()).toEqual(before);
    }
    if (width <= 1000)
      await page
        .getByRole("button", { name: "Apri menu", exact: true })
        .click();
    await page.getByRole("button", { name: "Manga 0", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Nessun titolo trovato" }),
    ).toBeVisible();
    expect(await frame()).toEqual(before);
  });
}
