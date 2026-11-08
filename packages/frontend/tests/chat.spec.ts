import { expect, test, type Page } from "@playwright/test";
import { account } from "./account";
import title from "./title.json" with { type: "json" };

async function mockCatalog(page: Page): Promise<URL[]> {
  const searches: URL[] = [];
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/search")) {
      searches.push(url);
      return route.fulfill({
        json: {
          items: [
            {
              title: {
                ...title,
                source_type: url.searchParams.get("source_type"),
                title: "Primo consiglio",
              },
              score: 0.91,
            },
            {
              title: {
                ...title,
                id: 2,
                source_type: url.searchParams.get("source_type"),
                title: "Secondo consiglio",
              },
              score: 0.82,
            },
          ],
          offset: 0,
          limit: 2,
        },
      });
    }
    return route.fulfill({
      json: url.pathname.endsWith("/auth/me")
        ? account
        : url.pathname.endsWith("/facets")
          ? { counts: {}, years: [], genres: [] }
          : /\/titles\/\d+$/.test(url.pathname)
            ? { ...title, title: "Primo consiglio" }
            : { items: [], total: 0, offset: 0, limit: 15 },
    });
  });
  return searches;
}

for (const width of [1440, 768, 390]) {
  test(`guided retrieval and title detail at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const searches = await mockCatalog(page);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Cosa vuoi farti consigliare?" }),
    ).toBeVisible();
    const input = page.getByRole("textbox", { name: "Messaggio", exact: true });
    const send = page.getByRole("button", {
      name: "Invia messaggio",
      exact: true,
    });
    await expect(send).toBeDisabled();
    await expect(input).toHaveAttribute("maxlength", "200");
    await page.screenshot({ path: `/tmp/musefy-retrieval-${width}-start.png` });
    const formats = page.getByRole("group", { name: "Formato da consigliare" });
    await formats.getByRole("button", { name: "Film", exact: true }).click();
    await expect(input).toBeFocused();
    await input.fill("   ");
    await input.press("Enter");
    expect(searches).toHaveLength(0);
    await input.fill("Un’indagine psicologica in una città inquietante");
    await input.press("Enter");
    const results = page.getByRole("link", { name: /^Apri .* consiglio$/ });
    await expect(results).toHaveText([/Primo consiglio/, /Secondo consiglio/]);
    expect(searches).toHaveLength(1);
    expect(Object.fromEntries(searches[0].searchParams)).toEqual({
      q: "Un’indagine psicologica in una città inquietante",
      source_type: "movie",
      limit: "2",
    });
    await expect(input).toHaveValue("");
    await page.screenshot({
      path: `/tmp/musefy-retrieval-${width}-results.png`,
    });
    await results.first().click();
    await expect(
      page
        .getByRole("dialog")
        .getByRole("heading", { name: "Primo consiglio", exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
    for (const [label, kind] of [
      ["Anime", "anime"],
      ["Manga", "manga"],
      ["Serie TV", "tv"],
    ]) {
      await formats.getByRole("button", { name: label, exact: true }).click();
      await expect(
        formats.getByRole("button", { name: label, exact: true }),
      ).toHaveAttribute("aria-pressed", "true");
      await input.fill("Prima riga");
      await input.press("Shift+Enter");
      await input.pressSequentially("Seconda riga");
      await send.click();
      await expect(
        page.locator(".chat-exchange").last().getByRole("link"),
      ).toHaveCount(2);
      expect(searches.at(-1)?.searchParams.get("source_type")).toBe(kind);
      expect(searches.at(-1)?.searchParams.get("q")).toBe(
        "Prima riga\nSeconda riga",
      );
    }
    await expect(page.locator(".chat-exchange")).toHaveCount(4);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <= innerWidth &&
          document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    await expect(send).toBeInViewport();
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Cosa vuoi farti consigliare?" }),
    ).toBeVisible();
    await expect(page.locator(".chat-exchange")).toHaveCount(0);
  });
}

test("one in-flight search, sanitized error and retry", async ({ page }) => {
  await mockCatalog(page);
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  let attempts = 0;
  await page.route("**/api/search?**", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await waiting;
      return route.fulfill({
        status: 503,
        json: { detail: "private debug information" },
      });
    }
    return route.fulfill({ json: { items: [], offset: 0, limit: 2 } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Anime", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Messaggio", exact: true });
  const send = page.getByRole("button", {
    name: "Invia messaggio",
    exact: true,
  });
  await input.fill("<script>alert('ciao')</script>");
  await input.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Cerco nel catalogo…");
  await input.fill("Altro messaggio");
  await expect(send).toBeDisabled();
  await input.press("Enter");
  expect(attempts).toBe(1);
  release();
  await expect(page.getByRole("alert")).toContainText(
    "La ricerca non è disponibile",
  );
  await expect(page.locator("body")).not.toContainText(
    "private debug information",
  );
  await expect(page.locator(".chat-message-user")).toContainText("<script>");
  await page.getByRole("button", { name: "Riprova la ricerca" }).click();
  await expect(page.locator(".chat-message-assistant")).toContainText(
    "Non ci sono ancora titoli indicizzati",
  );
  expect(attempts).toBe(2);
  await expect(page.locator(".chat-exchange")).toHaveCount(1);
});

test("expired session during retrieval returns to login", async ({ page }) => {
  await mockCatalog(page);
  await page.route("**/api/search?**", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Film", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Messaggio", exact: true });
  await input.fill("Una storia nello spazio");
  await input.press("Enter");
  await expect(
    page.getByRole("link", { name: "Continua con Google" }),
  ).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
});

for (const viewport of [
  { width: 320, height: 568 },
  { width: 844, height: 390 },
  { width: 768, height: 1024 },
]) {
  test(`mobile keyboard viewport at ${viewport.width}×${viewport.height}`, async ({
    browser,
  }) => {
    const context = await browser.newContext({
      viewport,
      isMobile: true,
      hasTouch: true,
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    try {
      await mockCatalog(page);
      await page.goto("/");
      const menu = page.getByRole("button", { name: "Apri menu", exact: true });
      const input = page.getByRole("textbox", {
        name: "Messaggio",
        exact: true,
      });
      const frame = () =>
        page.locator(".chat-composer").evaluate((element) => {
          const { x, y, width, height } = element.getBoundingClientRect();
          return { x, y, width, height };
        });
      const before = await frame();
      await menu.tap();
      const dialog = page.getByRole("dialog", { name: "Navigazione Musefy" });
      await expect(dialog).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "Chiudi menu", exact: true }),
      ).toBeInViewport();
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
      await expect(menu).toBeFocused();
      expect(await frame()).toEqual(before);
      await page.getByRole("button", { name: "Anime", exact: true }).tap();
      await input.fill("Una riga\n".repeat(16));
      const visibleHeight = Math.round(viewport.height * 0.6);
      await page.evaluate((height) => {
        const viewport = window.visualViewport!;
        Object.defineProperty(viewport, "height", {
          configurable: true,
          value: height,
        });
        Object.defineProperty(viewport, "offsetTop", {
          configurable: true,
          value: 12,
        });
        viewport.dispatchEvent(new Event("resize"));
      }, visibleHeight);
      const keyboardFrame = await frame();
      expect(keyboardFrame.y + keyboardFrame.height).toBeLessThanOrEqual(
        visibleHeight + 12,
      );
      expect(keyboardFrame.y).toBeGreaterThanOrEqual(52);
      await page
        .getByRole("button", { name: "Invia messaggio", exact: true })
        .tap();
      await expect(
        page.locator(".chat-message-assistant").getByRole("link"),
      ).toHaveCount(2);
      await page.evaluate(() => {
        const viewport = window.visualViewport!;
        Reflect.deleteProperty(viewport, "height");
        Reflect.deleteProperty(viewport, "offsetTop");
        viewport.dispatchEvent(new Event("resize"));
      });
      await expect(
        page.getByRole("button", { name: "Invia messaggio", exact: true }),
      ).toBeInViewport();
      expect(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth <= innerWidth &&
            document.documentElement.scrollHeight <= innerHeight,
        ),
      ).toBe(true);
    } finally {
      await context.close();
    }
  });
}

test("sidebar adapts without losing recommendations", async ({ page }) => {
  await mockCatalog(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "Film", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Messaggio", exact: true });
  await input.fill("Resta qui");
  await input.press("Enter");
  await expect(
    page.locator(".chat-message-assistant").getByRole("link"),
  ).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("navigation", { name: "Navigazione principale" }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "Apri menu", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navigazione principale" }),
  ).toBeVisible();
  await expect(page.locator("body")).not.toHaveAttribute("data-scroll-locked");
  await expect(page.locator(".chat-message-user")).toContainText("Resta qui");
  await expect(
    page.locator(".chat-message-assistant").getByRole("link"),
  ).toHaveCount(2);
});
