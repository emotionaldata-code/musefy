import { apiFetch, sessionExpiredEvent } from "./api";
import type { components } from "./api-schema";

export type CommunityList = components["schemas"]["ListSummary"];
export type CommunityListPage = components["schemas"]["ListPage"];
export type ListInput = components["schemas"]["ListInput"];
export type ListShareResponse = components["schemas"]["ListShare"];
export const communityPageSize = 20;

export function listPath(id: string, suffix = "", share: string | null = null) {
  const path = `/lists/${encodeURIComponent(id)}${suffix}`;
  return share ? `${path}?${new URLSearchParams({ share })}` : path;
}

export function pagedPath(path: string, q = "", offset = 0) {
  const params = new URLSearchParams({
    q,
    offset: String(offset),
    limit: String(communityPageSize),
  });
  return `${path}${path.includes("?") ? "&" : "?"}${params}`;
}

export async function communityRequest<T = void>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await apiFetch(path, options);
  if (response.status === 401) {
    window.dispatchEvent(new Event(sessionExpiredEvent));
    throw new Error("La sessione è scaduta. Accedi di nuovo.");
  }
  if (!response.ok)
    throw new Error(
      response.status === 404
        ? "La lista non è disponibile. Potrebbe essere privata o il link revocato."
        : response.status === 403
          ? "Non puoi modificare questa lista."
          : `Operazione non riuscita (HTTP ${response.status}). Riprova.`,
    );
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export function saveList(
  path: string,
  method: "POST" | "PUT",
  input: ListInput,
) {
  return communityRequest<CommunityList>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function sharedListURL(id: string, token: string | null = null) {
  const url = new URL(window.location.pathname, window.location.origin);
  url.search = new URLSearchParams({
    view: "lists",
    list: id,
    ...(token ? { share: token } : {}),
  }).toString();
  return url.href;
}
