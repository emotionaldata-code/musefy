import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`chat echoes messages and sidebar toggles at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.route("**/api/**", (route) =>
      route.fulfill({
        json: route.request().url().includes("/facets")
          ? { counts: {}, years: [], genres: [] }
          : { items: [], total: 0, offset: 0, limit: 15 },
      }),
    );
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Musefy");
    const navigation = page.getByRole("navigation", {
      name: "Navigazione principale",
    });
    if (width <= 1000) {
      await expect(navigation).not.toBeVisible();
      await page
        .getByRole("button", { name: "Apri menu", exact: true })
        .click();
    }
    await expect(navigation.getByRole("button").first()).toHaveText("Musefy");
    await expect(navigation.getByRole("button").first()).toHaveAttribute(
      "aria-current",
      "page",
    );
    if (width <= 1000) {
      await page
        .getByRole("button", { name: "Chiudi menu", exact: true })
        .click();
    }
    const input = page.getByRole("textbox", { name: "Messaggio", exact: true });
    const send = page.getByRole("button", {
      name: "Invia messaggio",
      exact: true,
    });
    await expect(send).toBeDisabled();
    await input.fill("   ");
    await input.press("Enter");
    await expect(page.locator(".chat-message")).toHaveCount(0);
    await input.fill("Un film per stasera?");
    await input.press("Enter");
    await expect(page.locator(".chat-message p")).toHaveText([
      "Un film per stasera?",
      "Un film per stasera?",
    ]);
    await expect(input).toHaveValue("");
    await expect(input).toBeFocused();
    await input.fill("Prima riga");
    await input.press("Shift+Enter");
    await input.pressSequentially("Seconda riga");
    await send.click();
    await expect(page.locator(".chat-message-assistant p").last()).toHaveText(
      "Prima riga\nSeconda riga",
    );
    if (width <= 1000) {
      await page
        .getByRole("button", { name: "Apri menu", exact: true })
        .click();
    }
    await page
      .getByRole("button", {
        name: width <= 1000 ? "Chiudi menu" : "Chiudi sidebar",
        exact: true,
      })
      .click();
    await expect(navigation).not.toBeVisible();
    await expect(
      page.getByRole("button", {
        name: width <= 1000 ? "Apri menu" : "Apri sidebar",
        exact: true,
      }),
    ).toHaveAttribute("aria-expanded", "false");
    await input.fill("Sidebar chiusa");
    await input.press("Enter");
    await expect(page.locator(".chat-message-assistant p").last()).toHaveText(
      "Sidebar chiusa",
    );
    await page
      .getByRole("button", {
        name: width <= 1000 ? "Apri menu" : "Apri sidebar",
        exact: true,
      })
      .click();
    await expect(navigation).toBeVisible();
    await navigation
      .getByRole("button", { name: "Manga 0", exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Manga");
    if (width <= 1000) {
      await page
        .getByRole("button", { name: "Apri menu", exact: true })
        .click();
    }
    await page
      .getByRole("button", {
        name: width <= 1000 ? "Chiudi menu" : "Chiudi sidebar",
        exact: true,
      })
      .click();
    await expect(navigation).not.toBeVisible();
    await page
      .getByRole("button", {
        name: width <= 1000 ? "Apri menu" : "Apri sidebar",
        exact: true,
      })
      .click();
    await navigation
      .getByRole("button", { name: "Musefy", exact: true })
      .click();
    if (width <= 1000) await expect(navigation).not.toBeVisible();
    await expect(page).not.toHaveURL(/view=catalog/);
    await expect(page.locator(".chat-message-assistant p")).toHaveCount(3);
    await input.fill("<script>alert('ciao')</script> " + "x".repeat(300));
    await input.press("Enter");
    await expect(
      page.locator(".chat-message-assistant p").last(),
    ).toContainText("<script>");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    for (let index = 0; index < 12; index += 1) {
      await input.fill(`Messaggio ${index + 1}`);
      await input.press("Enter");
    }
    await expect(page.locator(".chat-message-assistant p")).toHaveCount(16);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    await expect(send).toBeInViewport();
    await page.reload();
    if (width <= 1000) await expect(navigation).not.toBeVisible();
    else await expect(navigation).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Scrivi a Musefy" }),
    ).toBeVisible();
  });
}

for (const viewport of [
  { width: 320, height: 568 },
  { width: 844, height: 390 },
  { width: 768, height: 1024 },
]) {
  test(`mobile menu and keyboard viewport at ${viewport.width}×${viewport.height}`, async ({
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
      await page.route("**/api/**", (route) =>
        route.fulfill({ json: { counts: {}, years: [], genres: [] } }),
      );
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
      const manga = dialog.getByRole("button", {
        name: "Manga 0",
        exact: true,
      });
      await manga.scrollIntoViewIfNeeded();
      await expect(manga).toBeInViewport();
      await expect(
        dialog.getByRole("button", { name: "Chiudi menu", exact: true }),
      ).toBeInViewport();
      expect(
        await dialog.evaluate(
          (element) => element.scrollWidth <= element.clientWidth,
        ),
      ).toBe(true);
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
      await expect(menu).toBeFocused();
      expect(await frame()).toEqual(before);
      await menu.tap();
      await page.mouse.click(viewport.width - 12, 100);
      await expect(dialog).not.toBeVisible();
      await input.fill("Una riga\n".repeat(16));
      await expect(
        page.getByRole("button", { name: "Invia messaggio", exact: true }),
      ).toBeInViewport();
      // Simulate an OS keyboard reducing only the visual viewport, as on iOS Safari.
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
      await expect(page.locator(".chat-message-assistant p")).toHaveText(
        "Una riga\n".repeat(16),
      );
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

test("sidebar adapts across the mobile breakpoint without losing chat", async ({
  page,
}) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({ json: { counts: {}, years: [], genres: [] } }),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Messaggio", exact: true });
  await input.fill("Resta qui");
  await input.press("Enter");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("navigation")).not.toBeVisible();
  await page.getByRole("button", { name: "Apri menu", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("navigation")).toBeVisible();
  await expect(page.locator("body")).not.toHaveAttribute("data-scroll-locked");
  await expect(page.locator(".chat-message-assistant p")).toHaveText(
    "Resta qui",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("navigation")).not.toBeVisible();
});
