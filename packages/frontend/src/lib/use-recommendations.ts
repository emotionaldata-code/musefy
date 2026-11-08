import { useEffect, useRef, useState } from "react";
import { request, type Kind } from "./api";
import type { components } from "./api-schema";

export type SearchHit = components["schemas"]["SearchHit"];
type SearchPage = components["schemas"]["SearchPage"];
const pageSize = 2;
type Reply =
  | { status: "loading" }
  | { status: "ready"; items: SearchHit[] }
  | { status: "error" };
export type Exchange = {
  id: string;
  text: string;
  kind: Kind;
  offset: number;
  reply: Reply;
};

export function useRecommendations() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controller.current?.abort();
      controller.current = null;
    },
    [],
  );

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
      limit: String(pageSize),
    });
    if (exchange.offset) params.set("offset", String(exchange.offset));
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
      if (controller.current === current) {
        controller.current = null;
        setPending(false);
      }
    }
  }

  function send(text: string, kind: Kind, offset = 0): boolean {
    if (controller.current || !text.trim()) return false;
    const exchange: Exchange = {
      id: crypto.randomUUID(),
      text: text.trim(),
      kind,
      offset,
      reply: { status: "loading" },
    };
    setExchanges((items) => [...items, exchange]);
    void load(exchange);
    return true;
  }

  const latest = exchanges.at(-1);
  const hasMore =
    latest?.reply.status === "ready" && latest.reply.items.length === pageSize;

  function more(): void {
    if (latest && hasMore)
      send(latest.text, latest.kind, latest.offset + pageSize);
  }

  function reset(): void {
    controller.current?.abort();
    controller.current = null;
    setPending(false);
    setExchanges([]);
  }

  return { exchanges, pending, hasMore, send, more, reset, retry: load };
}
