import type { components } from "./api-schema";

export type Title = components["schemas"]["LibraryTitle"];
export type TitlePage = components["schemas"]["LibraryPage"];
export type Collection = components["schemas"]["Collection"];
export type LibraryState = components["schemas"]["LibraryState"];
export type AppView = "chat" | "catalog" | "lists" | "discover" | Collection;
export type Facets = components["schemas"]["CatalogFacets"];
export type Kind = components["schemas"]["Kind"];
export type Source = components["schemas"]["Source"];
export type Credit = components["schemas"]["Credit"];
export type CatalogQuery = {
  q: string;
  source: string;
  source_type: string;
  year: string;
  genre: string;
};

export const categories: { value: Kind | ""; label: string }[] = [
  { value: "", label: "Tutti i titoli" },
  { value: "movie", label: "Film" },
  { value: "tv", label: "Serie TV" },
  { value: "anime", label: "Anime" },
  { value: "manga", label: "Manga" },
];
export const categoryName = (kind: Kind): string =>
  categories.find((item) => item.value === kind)?.label ?? kind;
export const pageSize = 15;
export const apiBaseURL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(
  /\/$/,
  "",
);
export const docsURL = `${apiBaseURL}/docs`;
export const sessionExpiredEvent = "musefy:session-expired";

export function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  return fetch(`${apiBaseURL}${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
  });
}

export async function request<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await apiFetch(path, { signal });
  if (response.status === 401) {
    window.dispatchEvent(new Event(sessionExpiredEvent));
    throw new Error("La sessione è scaduta. Accedi di nuovo.");
  }
  if (!response.ok)
    throw new Error(
      response.status === 404
        ? "La scheda non è disponibile."
        : `Impossibile leggere il catalogo (HTTP ${response.status}).`,
    );
  return response.json() as Promise<T>;
}

export function titlesPath(
  query: CatalogQuery,
  offset = 0,
  collection?: Collection,
): string {
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(offset),
  });
  for (const [key, value] of Object.entries(query)) {
    if (value !== "") params.set(key, value);
  }
  return `${collection ? `/library/${collection}` : "/titles"}?${params}`;
}
