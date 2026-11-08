import { useSyncExternalStore } from "react";

const media = window.matchMedia("(max-width: 1000px)");

function subscribe(changed: () => void): () => void {
  media.addEventListener("change", changed);
  return () => media.removeEventListener("change", changed);
}

export function useMobile(): boolean {
  return useSyncExternalStore(subscribe, () => media.matches);
}
