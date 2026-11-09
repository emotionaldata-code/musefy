import { useEffect, useRef, useState } from "react";
import { communityRequest } from "./community";

export function useCommunityResource<T>(path: string | null, revision = 0) {
  const key = `${path}:${revision}`;
  const [state, setState] = useState<{
    key: string;
    path: string;
    data: T | null;
    error: string | null;
  } | null>(null);
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    communityRequest<T>(path, { signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted)
          setState({ key, path, data, error: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            key,
            path,
            data: null,
            error:
              error instanceof Error
                ? error.message
                : "Connessione non disponibile. Riprova.",
          });
      },
    );
    return () => controller.abort();
  }, [key, path]);
  return state?.key === key
    ? { ...state, loading: false }
    : {
        data: state?.path === path ? state.data : null,
        error: null,
        loading: path !== null,
      };
}

export function useCommunityMutation() {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(operation: () => Promise<unknown>) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      await operation();
      return true;
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Operazione non riuscita. Riprova.",
      );
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { busy, error, run };
}

export function useCommunitySearch(value: string) {
  const [query, setQuery] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(value.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [value]);
  return query;
}
