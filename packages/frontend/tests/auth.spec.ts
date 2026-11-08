import { expect, test } from "@playwright/test";
import { account } from "./account";

for (const width of [1440, 390]) {
  test(`unauthenticated visitors see only login at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    const protectedRequests: string[] = [];
    await page.route("**/api/**", async (route) => {
      if (!route.request().url().includes("/auth/me"))
        protectedRequests.push(route.request().url());
      await route.fulfill({ status: 401, json: {} });
    });
    await page.goto("/?view=catalog&source_type=anime#title/12");
    await expect(
      page.getByRole("heading", { name: "Accedi a Musefy" }),
    ).toBeVisible();
    await expect(page.getByRole("navigation")).toHaveCount(0);
    await expect(page.getByRole("textbox")).toHaveCount(0);
    const button = page.getByRole("link", { name: "Continua con Google" });
    const href = await button.getAttribute("href");
    const target = new URL(href!, page.url());
    expect(target.pathname).toBe("/api/auth/google");
    expect(target.searchParams.get("return_to")).toBe(
      "/?view=catalog&source_type=anime#title/12",
    );
    expect(protectedRequests).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });

  test(`account menu and logout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    let logoutMethod: string | undefined;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/auth/logout")) {
        logoutMethod = route.request().method();
        return route.fulfill({ status: 204 });
      }
      return route.fulfill({
        json: path.endsWith("/auth/me")
          ? account
          : { counts: {}, years: [], genres: [] },
      });
    });
    await page.goto("/");
    await page
      .getByRole("button", { name: `Account: ${account.email}` })
      .click();
    await expect(page.getByRole("menu").getByText(account.email)).toBeVisible();
    await page.getByRole("menuitem", { name: "Esci", exact: true }).click();
    await expect(
      page.getByRole("link", { name: "Continua con Google" }),
    ).toBeVisible();
    expect(logoutMethod).toBe("POST");
    await expect(page.getByRole("textbox")).toHaveCount(0);
    expect(
      await page.evaluate(() =>
        Object.keys(localStorage).filter((key) => /token|jwt|auth/i.test(key)),
      ),
    ).toEqual([]);
  });
}

test("checks session before protected content and retries a failed check", async ({
  page,
}) => {
  let fail = true;
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  const requests: string[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    if (path.endsWith("/auth/me")) {
      await waiting;
      return route.fulfill({
        status: fail ? 503 : 200,
        json: fail ? {} : account,
      });
    }
    return route.fulfill({ json: { counts: {}, years: [], genres: [] } });
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Verifica dell’accesso…");
  expect(requests.every((path) => path.endsWith("/auth/me"))).toBe(true);
  release();
  await expect(page.getByRole("alert")).toContainText(
    "Non riusciamo a verificare",
  );
  fail = false;
  await page.getByRole("button", { name: "Riprova" }).click();
  await expect(
    page.getByRole("textbox", { name: "Messaggio", exact: true }),
  ).toBeVisible();
});

test("expired sessions unmount protected content", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: account }),
  );
  await page.route("**/api/titles**", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await page.goto("/?view=catalog");
  await expect(
    page.getByRole("link", { name: "Continua con Google" }),
  ).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
});

test("callback errors are generic and removed from return destination", async ({
  page,
}) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await page.goto("/?view=catalog&auth_error=private-provider-detail");
  await expect(page.getByRole("alert")).toHaveText(
    "Accesso non completato. Puoi riprovare con Google.",
  );
  await expect(page.locator("body")).not.toContainText(
    "private-provider-detail",
  );
  const href = await page
    .getByRole("link", { name: "Continua con Google" })
    .getAttribute("href");
  expect(new URL(href!, page.url()).searchParams.get("return_to")).toBe(
    "/?view=catalog",
  );
});
