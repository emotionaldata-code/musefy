import { expect, test, type Page } from "@playwright/test";
import { account } from "./account";
import title from "./title.json" with { type: "json" };

const listId = "11111111-1111-4111-8111-111111111111";
const token = "22222222-2222-4222-8222-222222222222";
const sharedURL = `/?view=lists&list=${listId}&share=${token}`;
const summary = {
  id: listId,
  name: "Cinema del weekend",
  description: "Storie da vedere insieme.",
  owner: { id: 1, name: "Tester Musefy", picture: null },
  is_owner: true,
  is_public: false,
  is_following: false,
  item_count: 1,
  follower_count: 0,
  created_at: "2026-11-09T10:00:00Z",
  updated_at: "2026-11-09T10:00:00Z",
};

async function backend(page: Page, owner = true) {
  let list = { ...summary, is_owner: owner, is_public: !owner };
  let items = [title];
  const changes: string[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();
    if (path === "/auth/me") return route.fulfill({ json: account });
    if (path === "/titles/facets")
      return route.fulfill({ json: { counts: {}, years: [], genres: [] } });
    if (path === "/lists" && method === "POST") {
      list = { ...list, ...request.postDataJSON() };
      changes.push("create");
      return route.fulfill({ json: list });
    }
    if (path === `/lists/${listId}`) {
      if (method === "PUT") {
        list = { ...list, ...request.postDataJSON() };
        changes.push("save");
      }
      if (method === "DELETE") {
        changes.push("delete");
        return route.fulfill({ status: 204 });
      }
      return route.fulfill({ json: { ...list, item_count: items.length } });
    }
    if (path === `/lists/${listId}/share`) {
      changes.push(method === "POST" ? "share" : "revoke");
      return route.fulfill(
        method === "POST" ? { json: { token } } : { status: 204 },
      );
    }
    if (path === `/lists/${listId}/follow`) {
      list = { ...list, is_following: method === "PUT" };
      changes.push(method === "PUT" ? "follow" : "unfollow");
      return route.fulfill({ status: 204 });
    }
    if (path === `/lists/${listId}/items/${title.id}`) {
      items = method === "PUT" ? [title] : [];
      changes.push(method === "PUT" ? "add" : "remove");
      return route.fulfill({ status: 204 });
    }
    if (path === `/lists/${listId}/items` || path === "/titles") {
      return route.fulfill({
        json: {
          items: path === "/titles" ? [title] : items,
          total: path === "/titles" ? 1 : items.length,
          offset: 0,
          limit: 20,
        },
      });
    }
    if (["/lists/mine", "/lists/discover", "/lists/following"].includes(path)) {
      const entries =
        path === "/lists/mine"
          ? owner && !changes.includes("delete")
            ? [list]
            : []
          : path === "/lists/following"
            ? list.is_following
              ? [list]
              : []
            : [list];
      return route.fulfill({
        json: { items: entries, total: entries.length, offset: 0, limit: 20 },
      });
    }
    return route.fulfill({ status: 404, json: {} });
  });
  return {
    changes,
    setPrivate: () => {
      list = { ...list, is_public: false };
    },
  };
}

for (const width of [1440, 390, 320]) {
  test(`create, curate, publish and delete a list at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const { changes } = await backend(page);
    await page.goto("/?view=lists");
    await page
      .getByRole("button", { name: "Nuova lista", exact: true })
      .click();
    await page.getByLabel("Nome", { exact: true }).fill("Serate d’autunno");
    await page
      .getByLabel("Descrizione", { exact: false })
      .fill("Film per le prossime serate.");
    await page.getByRole("button", { name: "Crea lista", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`list=${listId}`));
    await expect(
      page.getByRole("heading", { name: "Serate d’autunno", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Pubblica", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Rendi privata", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Modifica", exact: true }).click();
    await page.getByLabel("Nome", { exact: true }).fill("Cinema d’autunno");
    await page
      .getByRole("button", { name: "Salva modifiche", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Cinema d’autunno", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: `Rimuovi dalla lista: ${title.title}`,
        exact: true,
      })
      .click();
    await expect(
      page.getByText("La lista è vuota.", { exact: false }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Aggiungi titoli", exact: true })
      .click();
    await page
      .getByRole("searchbox", { name: "Cerca titoli da aggiungere" })
      .fill("storia");
    await page
      .getByRole("button", { name: `Aggiungi: ${title.title}`, exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: `Aggiunto: ${title.title}`,
        exact: true,
      }),
    ).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("link", { name: `Apri ${title.title}`, exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Torna alle liste", exact: false })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: /Cinema d’autunno.*Apri/ }).click();
    await page
      .getByRole("button", { name: "Elimina lista", exact: true })
      .click();
    expect(changes).not.toContain("delete");
    await page
      .getByRole("button", { name: "Elimina definitivamente", exact: true })
      .click();
    await expect(page).not.toHaveURL(/list=/);
    expect(changes).toEqual(
      expect.arrayContaining(["create", "save", "remove", "add", "delete"]),
    );
  });
}

test("shared readers can follow public lists and cannot edit private previews", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async () => {} },
    });
  });
  const server = await backend(page, false);
  await page.goto(sharedURL);
  await expect(
    page.getByRole("link", { name: `Apri ${title.title}`, exact: true }),
  ).toBeVisible();
  for (const name of [
    "Modifica",
    "Pubblica",
    "Rendi privata",
    "Aggiungi titoli",
    "Elimina lista",
    "Revoca link",
  ])
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
      0,
    );
  await expect(
    page.getByRole("button", { name: "Rimuovi dalla lista", exact: false }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Segui lista", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Non seguire più", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Condividi", exact: true }).click();
  await expect(page.getByLabel("Link di lettura")).toHaveValue(
    new RegExp(`view=lists&list=${listId}$`),
  );
  expect(server.changes).not.toContain("share");
  server.setPrivate();
  await page.reload();
  await expect(
    page.getByText("Questa lista privata è condivisa con te in sola lettura."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Segui lista|Non seguire più/ }),
  ).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`share=${token}`));
  await page.getByRole("button", { name: "Condividi", exact: true }).click();
  await expect(page.getByLabel("Link di lettura")).toHaveValue(
    new RegExp(`share=${token}$`),
  );
  expect(server.changes).not.toContain("share");
});

test("sharing preserves a selectable link when clipboard fails and allows revocation", async ({
  page,
}) => {
  const { changes } = await backend(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("blocked");
        },
      },
    });
  });
  await page.goto(`/?view=lists&list=${listId}`);
  await page.getByRole("button", { name: "Condividi", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Seleziona e copia il link",
  );
  await expect(page.getByLabel("Link di lettura")).toHaveValue(
    new RegExp(`view=lists&list=${listId}&share=${token}`),
  );
  await page.getByRole("button", { name: "Revoca link", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Link revocato");
  await expect(page.getByLabel("Link di lettura")).toHaveCount(0);
  expect(changes).toEqual(["share", "revoke"]);
});

test("failed writes preserve visible state and title search can retry", async ({
  page,
}) => {
  await backend(page);
  await page.route(`**/api/lists/${listId}`, async (route) =>
    route.request().method() === "PUT"
      ? route.fulfill({ status: 503 })
      : route.fallback(),
  );
  await page.route(`**/api/lists/${listId}/share`, (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.goto(`/?view=lists&list=${listId}`);
  await page.getByRole("button", { name: "Pubblica", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("HTTP 503");
  await expect(
    page.getByRole("button", { name: "Pubblica", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "Condividi", exact: true }).click();
  await expect(
    page.locator(".community-share").getByRole("alert"),
  ).toContainText("HTTP 503");
  await page.getByRole("button", { name: "Revoca link", exact: true }).click();
  await expect(
    page.locator(".community-share").getByRole("alert"),
  ).toContainText("HTTP 503");
  await page.route("**/api/titles?**", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page
    .getByRole("button", { name: "Aggiungi titoli", exact: true })
    .click();
  await page
    .getByRole("searchbox", { name: "Cerca titoli da aggiungere" })
    .fill("storia");
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "HTTP 503",
  );
  await page.unroute("**/api/titles?**");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Riprova", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: `Aggiungi: ${title.title}`, exact: true }),
  ).toBeVisible();
});

test("discovery search resets pagination", async ({ page }) => {
  await backend(page, false);
  const offsets: number[] = [];
  await page.route("**/api/lists/discover?**", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset"));
    offsets.push(offset);
    const q = params.get("q");
    const items =
      q === "vuoto"
        ? []
        : Array.from({ length: offset ? 1 : 20 }, (_, index) => ({
            ...summary,
            id: String(offset + index),
            name: `Raccolta ${offset + index + 1}`,
            is_owner: false,
            is_public: true,
          }));
    await route.fulfill({
      json: { items, total: q === "vuoto" ? 0 : 21, offset, limit: 20 },
    });
  });
  await page.goto("/?view=discover");
  await page.getByRole("button", { name: "Successive", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Raccolta 21", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("searchbox", { name: "Cerca liste", exact: true })
    .fill("vuoto");
  await expect(
    page.getByText("Nessuna lista trovata. Prova un altro nome."),
  ).toBeVisible();
  expect(
    offsets.filter(
      (offset, index) => index === 0 || offset !== offsets[index - 1],
    ),
  ).toEqual([0, 20, 0]);
});

test("shared links survive the unauthenticated login handoff", async ({
  page,
}) => {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 401 }));
  await page.goto(sharedURL);
  const href = await page
    .getByRole("link", { name: "Continua con Google" })
    .getAttribute("href");
  expect(new URL(href!, "http://localhost").searchParams.get("return_to")).toBe(
    sharedURL,
  );
});
