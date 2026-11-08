import { useCallback, useEffect, useState } from "react";
import { apiFetch, sessionExpiredEvent } from "./api";
import type { components } from "./api-schema";

export type Account = components["schemas"]["User"];

type AuthState =
  | { status: "checking"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "error"; user: null }
  | { status: "authenticated"; user: Account };

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    status: "checking",
    user: null,
  });
  const [attempt, setAttempt] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const expired = () => setState({ status: "anonymous", user: null });
    window.addEventListener(sessionExpiredEvent, expired);
    apiFetch("/auth/me", { signal: controller.signal })
      .then(async (response) => {
        if (response.status === 401) {
          if (!controller.signal.aborted) expired();
          return;
        }
        if (!response.ok) throw new Error("Session check failed");
        const user = (await response.json()) as Account;
        if (!controller.signal.aborted)
          setState({ status: "authenticated", user });
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setState({ status: "error", user: null });
      });
    return () => {
      controller.abort();
      window.removeEventListener(sessionExpiredEvent, expired);
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "checking", user: null });
    setAttempt((value) => value + 1);
  }, []);

  async function logout() {
    setLoggingOut(true);
    setLogoutError(false);
    try {
      const response = await apiFetch("/auth/logout", { method: "POST" });
      if (!response.ok && response.status !== 401)
        throw new Error("Logout failed");
      setState({ status: "anonymous", user: null });
    } catch {
      setLogoutError(true);
    } finally {
      setLoggingOut(false);
    }
  }

  return { ...state, retry, logout, loggingOut, logoutError };
}
