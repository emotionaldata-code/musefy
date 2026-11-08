import {
  createContext,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  apiFetch,
  sessionExpiredEvent,
  type Collection,
  type LibraryState,
  type Title,
} from "./api";

const empty: LibraryState = { watched: false, wishlist: false };

function useLibraryStore() {
  const [states, setStates] = useState<Record<number, LibraryState>>({});
  const [pending, setPending] = useState<Record<number, boolean>>({});
  const [errors, setErrors] = useState<Record<number, string | undefined>>({});
  const [revisions, setRevisions] = useState({ watched: 0, wishlist: 0 });
  const locks = useRef(new Set<number>());

  function state(title: Title): LibraryState {
    return states[title.id] ?? title.library ?? empty;
  }

  async function toggle(title: Title, collection: Collection): Promise<void> {
    if (locks.current.has(title.id)) return;
    locks.current.add(title.id);
    setPending((current) => ({ ...current, [title.id]: true }));
    setErrors((current) => ({ ...current, [title.id]: undefined }));
    try {
      const response = await apiFetch(`/library/${collection}/${title.id}`, {
        method: state(title)[collection] ? "DELETE" : "PUT",
      });
      if (response.status === 401) {
        window.dispatchEvent(new Event(sessionExpiredEvent));
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const saved = (await response.json()) as LibraryState;
      setStates((current) => ({ ...current, [title.id]: saved }));
      setRevisions((current) => ({
        ...current,
        [collection]: current[collection] + 1,
      }));
    } catch {
      setErrors((current) => ({
        ...current,
        [title.id]: "Salvataggio non riuscito. Riprova con il pulsante.",
      }));
    } finally {
      locks.current.delete(title.id);
      setPending((current) => ({ ...current, [title.id]: false }));
    }
  }

  function refresh() {
    setStates({});
    setErrors({});
  }

  return { state, toggle, pending, errors, revisions, refresh };
}

const LibraryContext = createContext<ReturnType<typeof useLibraryStore> | null>(
  null,
);

export function LibraryProvider({ children }: { children: ReactNode }) {
  const library = useLibraryStore();
  return <LibraryContext value={library}>{children}</LibraryContext>;
}

// oxlint-disable-next-line react/only-export-components -- Shared account-scoped context and hook.
export function useLibrary() {
  const library = useContext(LibraryContext);
  if (!library) throw new Error("LibraryProvider is missing");
  return library;
}
