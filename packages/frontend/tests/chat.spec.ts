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
    await expect(navigation.getByRole("button").first()).toHaveText("Musefy");
    await expect(navigation.getByRole("button").first()).toHaveAttribute(
      "aria-current",
      "page",
    );
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
    await page
      .getByRole("button", { name: "Chiudi sidebar", exact: true })
      .click();
    await expect(navigation).not.toBeVisible();
    await expect(
      page.getByRole("button", { name: "Apri sidebar", exact: true }),
    ).toHaveAttribute("aria-expanded", "false");
    await input.fill("Sidebar chiusa");
    await input.press("Enter");
    await expect(page.locator(".chat-message-assistant p").last()).toHaveText(
      "Sidebar chiusa",
    );
    await page
      .getByRole("button", { name: "Apri sidebar", exact: true })
      .click();
    await expect(navigation).toBeVisible();
    await navigation
      .getByRole("button", { name: "Manga 0", exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Manga");
    await page
      .getByRole("button", { name: "Chiudi sidebar", exact: true })
      .click();
    await expect(navigation).not.toBeVisible();
    await page
      .getByRole("button", { name: "Apri sidebar", exact: true })
      .click();
    await navigation
      .getByRole("button", { name: "Musefy", exact: true })
      .click();
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
    await expect(navigation).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Scrivi a Musefy" }),
    ).toBeVisible();
  });
}
