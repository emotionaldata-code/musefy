import type { components } from "./api-schema";

export type Title = components["schemas"]["StoredTitle"];
export type TitlePage = components["schemas"]["TitlePage"];
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
  offset: number;
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
export const docsURL = `${import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"}/docs`;

export async function request<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const baseURL = import.meta.env.VITE_API_BASE_URL ?? "/api";
  const response = await fetch(`${baseURL}${path}`, { signal });
  if (!response.ok)
    throw new Error(
      response.status === 404
        ? "La scheda non è disponibile."
        : `Impossibile leggere il catalogo (HTTP ${response.status}).`,
    );
  return response.json() as Promise<T>;
}

export function titlesPath(query: CatalogQuery): string {
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(query.offset),
  });
  for (const [key, value] of Object.entries(query)) {
    if (value !== "" && key !== "offset") params.set(key, String(value));
  }
  return `/titles?${params}`;
}
