import { expect, test, type Page } from "@playwright/test";
import { account } from "./account";
import fixture from "./title.json" with { type: "json" };

type State = { watched: boolean; wishlist: boolean };
async function backend(page: Page, count = 4) {
  const states = new Map<number, State>();
  const kinds = ["movie", "tv", "anime", "manga"];
  const titles = Array.from({ length: count }, (_, index) => ({
    ...fixture,
    id: index + 1,
    title: index === 0 ? fixture.title : `Opera ${index + 1}`,
    source: index % 4 < 2 ? "tmdb" : "jikan",
    source_type: kinds[index % 4],
  }));
  const state = (id: number) =>
    states.get(id) ?? { watched: false, wishlist: false };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    if (path === "/auth/me") return route.fulfill({ json: account });
    if (path === "/titles/facets")
      return route.fulfill({
        json: {
          counts: { movie: 1, tv: 1, anime: 1, manga: 1 },
          years: [2020],
          genres: ["Drama"],
        },
      });
    const membership = /^\/library\/(watched|wishlist)\/(\d+)$/.exec(path);
    if (membership) {
      const id = Number(membership[2]);
      const saved = {
        ...state(id),
        [membership[1]]: route.request().method() === "PUT",
      };
      states.set(id, saved);
      expect(route.request().postData()).toBeNull();
      return route.fulfill({ json: saved });
    }
    const detail = /^\/titles\/(\d+)$/.exec(path);
    if (detail)
      return route.fulfill({
        json: {
          ...titles.find((title) => title.id === Number(detail[1])),
          library: state(Number(detail[1])),
        },
      });
    const collection = path.split("/")[2] as keyof State | undefined;
    let items = titles.filter(
      (title) => !collection || state(title.id)[collection],
    );
    const kind = url.searchParams.get("source_type");
    const query = url.searchParams.get("q");
    if (kind) items = items.filter((title) => title.source_type === kind);
    if (query) items = items.filter((title) => title.title.includes(query));
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 15);
    return route.fulfill({
      json: {
        items: items
          .slice(offset, offset + limit)
          .map((title) => ({ ...title, library: state(title.id) })),
        total: items.length,
        offset,
        limit,
      },
    });
  });
  return states;
}
async function openList(page: Page, label: string, mobile: boolean) {
  if (mobile)
    await page.getByRole("button", { name: "Apri menu", exact: true }).click();
  await page
    .getByRole("navigation", { name: "I tuoi elenchi" })
    .getByRole("button", { name: label, exact: true })
    .click();
}
for (const width of [1440, 768, 390]) {
  test(`saved lists persist and stay consistent at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const states = await backend(page);
    await page.goto("/?view=catalog");
    const card = page.locator(".title-card").first();
    const wishlist = card.getByRole("button", {
      name: "Wishlist: Una storia",
      exact: true,
    });
    await wishlist.click();
    await expect(wishlist).toHaveAttribute("aria-pressed", "true");
    await expect(page).not.toHaveURL(/#title/);
    await card
      .getByRole("button", { name: "Già visto: Una storia", exact: true })
      .click();
    await expect(
      card.getByRole("button", { name: "Già visto: Una storia", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.getByRole("button", { name: "Già letto: Opera 4", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: `/tmp/musefy-library-${width}.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await card.getByRole("link", { name: "Apri Una storia" }).click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("button", { name: "Wishlist: Una storia", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await dialog
      .getByRole("button", { name: "Wishlist: Una storia", exact: true })
      .click();
    await page.keyboard.press("Escape");
    await expect(wishlist).toHaveAttribute("aria-pressed", "false");
    await wishlist.click();
    await page.reload();
    await expect(
      page
        .locator(".title-card")
        .first()
        .getByRole("button", { name: "Wishlist: Una storia", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await openList(page, "Guarda più tardi", width <= 1000);
    await expect(page).toHaveURL(/view=wishlist/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Guarda più tardi",
    );
    await expect(page.locator(".title-card")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Wishlist: Una storia", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Il tuo elenco è ancora vuoto" }),
    ).toBeVisible();
    await openList(page, "Già visti", width <= 1000);
    await expect(page.locator(".title-card")).toHaveCount(1);
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Già visti",
    );
    expect(states.get(1)).toEqual({ watched: true, wishlist: false });
  });
}
test("failed writes preserve state, prevent duplicates and can be retried", async ({
  page,
}) => {
  await backend(page);
  let release: () => void = () => {};
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  let calls = 0;
  await page.route("**/api/library/wishlist/1", async (route) => {
    calls++;
    await blocked;
    await route.fulfill({ status: 503, json: {} });
  });
  await page.goto("/?view=catalog");
  const card = page.locator(".title-card").first();
  const wishlist = card.getByRole("button", {
    name: "Wishlist: Una storia",
    exact: true,
  });
  await wishlist.click();
  await expect(wishlist).toBeDisabled();
  await expect(
    card.getByRole("button", { name: "Già visto: Una storia", exact: true }),
  ).toBeDisabled();
  expect(calls).toBe(1);
  release();
  await expect(card.getByRole("alert")).toContainText(
    "Salvataggio non riuscito",
  );
  await expect(wishlist).toHaveAttribute("aria-pressed", "false");
  await page.unroute("**/api/library/wishlist/1");
  await wishlist.click();
  await expect(wishlist).toHaveAttribute("aria-pressed", "true");
  await expect(card.getByRole("alert")).toHaveCount(0);
});
test("removing a saved title does not skip the next page", async ({ page }) => {
  const states = await backend(page, 31);
  for (let id = 1; id <= 31; id++)
    states.set(id, { watched: false, wishlist: true });
  await page.goto("/?view=wishlist");
  await expect(page.locator(".title-card").first()).toBeVisible();
  await page
    .getByRole("button", { name: "Wishlist: Una storia", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Apri Una storia", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("link", { name: "Apri Opera 16", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("link", { name: "Apri Opera 31", exact: true }),
  ).toBeAttached();
  await expect(page.locator(".title-card")).toHaveCount(30);
  await expect(page.getByText("30 titoli visualizzati")).toBeVisible();
});
test("expired sessions during a write return to login", async ({ page }) => {
  await backend(page);
  await page.route("**/api/library/wishlist/1", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await page.goto("/?view=catalog");
  await page
    .getByRole("button", { name: "Wishlist: Una storia", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Continua con Google" }),
  ).toBeVisible();
  await expect(page.locator(".title-card")).toHaveCount(0);
});

test("refresh reads membership changes from another browser", async ({
  page,
}) => {
  const states = await backend(page);
  await page.goto("/?view=catalog");
  const wishlist = page.getByRole("button", {
    name: "Wishlist: Una storia",
    exact: true,
  });
  await wishlist.click();
  await expect(wishlist).toHaveAttribute("aria-pressed", "true");
  states.set(1, { watched: false, wishlist: false });
  await page.getByRole("button", { name: "Aggiorna catalogo" }).click();
  await expect(wishlist).toHaveAttribute("aria-pressed", "false");
});
