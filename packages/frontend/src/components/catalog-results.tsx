import { useEffect, useRef } from "react";
import { LoaderCircle, X } from "lucide-react";
import { Button } from "./ui/button";
import { Skeleton } from "./ui/skeleton";
import { TitleCard } from "./title-card";
import type { CatalogQuery, Collection } from "@/lib/api";
import { useCatalog } from "@/lib/use-catalog";

export function CatalogResults({
  query,
  reset,
  collection,
}: {
  query: CatalogQuery;
  reset: () => void;
  collection?: Collection;
}) {
  const { items, total, loading, done, error, loadMore, retry } = useCatalog(
    query,
    collection,
  );
  const sentinel = useRef<HTMLDivElement>(null);
  const filtered = !!(query.q || query.source || query.year || query.genre);

  useEffect(() => {
    const element = sentinel.current;
    if (!element || loading || done || error) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore();
      },
      { rootMargin: "600px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [loading, done, error, loadMore]);

  return (
    <>
      <div className="results-line" aria-live="polite">
        <span>
          {loading && !items.length
            ? "Caricamento…"
            : `${total.toLocaleString("it-IT")} titoli${filtered ? " trovati" : ""}`}
        </span>
        {filtered && (
          <button onClick={reset}>
            Rimuovi filtri <X size={12} />
          </button>
        )}
      </div>
      {items.length > 0 && (
        <div className="catalog-grid" aria-label="Titoli">
          {items.map((title) => (
            <TitleCard key={title.id} title={title} />
          ))}
        </div>
      )}
      {loading && !items.length && (
        <div className="catalog-grid" aria-label="Caricamento catalogo">
          {Array.from({ length: 10 }, (_, index) => (
            <div key={index}>
              <Skeleton className="aspect-[2/3] w-full rounded-lg" />
              <Skeleton className="mt-3 h-4 w-3/4" />
            </div>
          ))}
        </div>
      )}
      {error && (
        <div
          className={items.length ? "load-status" : "empty-state"}
          role="alert"
        >
          <p>
            {items.length
              ? "Non riesco a caricare altri titoli."
              : "Il catalogo non è raggiungibile."}{" "}
            {error}
          </p>
          <Button variant="outline" onClick={retry}>
            Riprova
          </Button>
        </div>
      )}
      {!loading && !error && !items.length && (
        <div className="empty-state">
          <h2>
            {filtered || query.source_type
              ? "Nessun titolo trovato"
              : collection
                ? "Il tuo elenco è ancora vuoto"
                : "La biblioteca è ancora vuota"}
          </h2>
          <p>
            {filtered || query.source_type
              ? "Prova un altro titolo o modifica i filtri."
              : collection === "wishlist"
                ? "Usa Wishlist sulle card per ritrovare qui i titoli da guardare o leggere."
                : collection === "watched"
                  ? "Segna i titoli come già visti o letti per ritrovarli qui."
                  : "Le opere importate compariranno qui."}
          </p>
          {(filtered || query.source_type) && (
            <Button variant="outline" onClick={reset}>
              Mostra tutti i titoli
            </Button>
          )}
        </div>
      )}
      <div
        ref={sentinel}
        className="load-status"
        role="status"
        aria-live="polite"
      >
        {loading && items.length > 0 && (
          <>
            <LoaderCircle className="loading-spinner" size={18} /> Caricamento…
          </>
        )}
        {done &&
          items.length > 0 &&
          `${items.length.toLocaleString("it-IT")} titoli visualizzati`}
      </div>
    </>
  );
}
