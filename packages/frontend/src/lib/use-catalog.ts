import { useEffect, useState } from "react";
import {
  request,
  titlesPath,
  type CatalogQuery,
  type Collection,
  type Title,
  type TitlePage,
} from "./api";

type CatalogState = {
  items: Title[];
  total: number;
  nextOffset: number;
  loading: boolean;
  done: boolean;
  error: string | null;
};

// The catalog component remounts on filter changes, cancelling the old request.
export function useCatalog(query: CatalogQuery, collection?: Collection) {
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<CatalogState>({
    items: [],
    total: 0,
    nextOffset: 0,
    loading: true,
    done: false,
    error: null,
  });
  const path = titlesPath(query, offset, collection);

  useEffect(() => {
    const controller = new AbortController();
    request<TitlePage>(path, controller.signal).then(
      (page) => {
        if (controller.signal.aborted) return;
        setState((current) => {
          const ids = new Set(current.items.map((title) => title.id));
          const nextOffset = page.offset + page.items.length;
          return {
            items: [
              ...current.items,
              ...page.items.filter((title) => !ids.has(title.id)),
            ],
            total: page.total,
            nextOffset,
            loading: false,
            done: page.items.length === 0 || nextOffset >= page.total,
            error: null,
          };
        });
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setState((current) => ({
            ...current,
            loading: false,
            error:
              error instanceof Error
                ? error.message
                : "Connessione non disponibile.",
          }));
      },
    );
    return () => controller.abort();
  }, [path, attempt]);

  function loadMore(): void {
    if (state.loading || state.done || state.error) return;
    setState((current) => ({ ...current, loading: true }));
    setOffset(state.nextOffset);
  }

  function retry(): void {
    setState((current) => ({ ...current, loading: true, error: null }));
    setAttempt((current) => current + 1);
  }

  return { ...state, loadMore, retry };
}
