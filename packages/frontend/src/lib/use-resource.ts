import { useEffect, useState } from "react";
import { request } from "./api";

type Resource<T> = { data: T | null; error: string | null; loading: boolean };

export function useResource<T>(path: string | null, revision = 0): Resource<T> {
  const key = `${revision}:${path}`;
  const [state, setState] = useState<{
    key: string;
    data: T | null;
    error: string | null;
  } | null>(null);
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    request<T>(path, controller.signal).then(
      (data) => setState({ key, data, error: null }),
      (error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            key,
            data: null,
            error:
              error instanceof Error
                ? error.message
                : "Connessione non disponibile.",
          });
      },
    );
    return () => controller.abort();
  }, [path, key]);
  if (path === null || state?.key !== key)
    return { data: null, error: null, loading: path !== null };
  return { ...state, loading: false };
}
