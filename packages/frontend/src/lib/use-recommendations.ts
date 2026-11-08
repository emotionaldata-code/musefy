import { useEffect, useRef, useState } from "react";
import { request, type Kind } from "./api";
import type { components } from "./api-schema";

export type SearchHit = components["schemas"]["SearchHit"];
type SearchPage = components["schemas"]["SearchPage"];
type Reply =
  | { status: "loading" }
  | { status: "ready"; items: SearchHit[] }
  | { status: "error" };
export type Exchange = {
  id: string;
  text: string;
  kind: Kind;
  reply: Reply;
};

export function useRecommendations() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function load(exchange: Exchange): Promise<void> {
    if (controller.current) return;
    const current = new AbortController();
    controller.current = current;
    setPending(true);
    function update(reply: Reply): void {
      setExchanges((items) =>
        items.map((item) =>
          item.id === exchange.id ? { ...item, reply } : item,
        ),
      );
    }
    update({ status: "loading" });
    const params = new URLSearchParams({
      q: exchange.text,
      source_type: exchange.kind,
      limit: "2",
    });
    try {
      const page = await request<SearchPage>(
        `/search?${params}`,
        current.signal,
      );
      if (!current.signal.aborted)
        update({ status: "ready", items: page.items });
    } catch {
      if (!current.signal.aborted) update({ status: "error" });
    } finally {
      controller.current = null;
      if (!current.signal.aborted) setPending(false);
    }
  }

  function send(text: string, kind: Kind): boolean {
    if (controller.current || !text.trim()) return false;
    const exchange: Exchange = {
      id: crypto.randomUUID(),
      text: text.trim(),
      kind,
      reply: { status: "loading" },
    };
    setExchanges((items) => [...items, exchange]);
    void load(exchange);
    return true;
  }

  return { exchanges, pending, send, retry: load };
}
