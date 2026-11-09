import { useState } from "react";
import { type CommunityListPage, pagedPath } from "@/lib/community";
import { useCommunityResource } from "@/lib/use-community";
import { Button } from "../ui/button";

export function CommunityStatus({
  error,
  retry,
}: {
  error: string;
  retry: () => void;
}) {
  return (
    <div className="community-status" role="alert">
      <p>{error}</p>
      <Button variant="outline" onClick={retry}>
        Riprova
      </Button>
    </div>
  );
}

export function ListPagination({
  total,
  offset,
  limit,
  onChange,
}: {
  total: number;
  offset: number;
  limit: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  return (
    <nav aria-label="Pagine delle liste" className="community-pagination">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} di {total}
      </span>
      <Button
        variant="outline"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        Precedenti
      </Button>
      <Button
        variant="outline"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        Successive
      </Button>
    </nav>
  );
}

export function ListIndex({
  scope,
  query,
  onSelect,
}: {
  scope: "mine" | "following" | "discover";
  query: string;
  onSelect: (id: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const result = useCommunityResource<CommunityListPage>(
    pagedPath(`/lists/${scope}`, query, offset),
    revision,
  );
  const heading =
    scope === "mine"
      ? "Create da te"
      : scope === "following"
        ? "Liste che segui"
        : "Liste della community";
  return (
    <section className="community-section" aria-label={heading}>
      <h2>
        {heading}
        {result.data ? <span>{result.data.total}</span> : null}
      </h2>
      {result.loading && (
        <p role="status" className="community-note">
          Caricamento liste…
        </p>
      )}
      {result.error && (
        <CommunityStatus
          error={result.error}
          retry={() => setRevision((value) => value + 1)}
        />
      )}
      {result.data && (
        <>
          {result.data.items.length ? (
            <div className="community-list-rows">
              {result.data.items.map((list) => (
                <button
                  className="community-list-row"
                  key={list.id}
                  onClick={() => onSelect(list.id)}
                >
                  <div className="community-list-copy">
                    <h3>{list.name}</h3>
                    {list.description && <p>{list.description}</p>}
                    <div className="community-list-meta">
                      <span>
                        {list.item_count}{" "}
                        {list.item_count === 1 ? "titolo" : "titoli"}
                      </span>
                      <span>
                        {list.is_owner
                          ? list.is_public
                            ? "Pubblica"
                            : "Privata"
                          : `di ${list.owner.name ?? "un utente Musefy"}`}
                      </span>
                      <span>{list.follower_count} follower</span>
                    </div>
                  </div>
                  <span className="community-open">Apri</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="community-empty">
              <p>
                {query
                  ? "Nessuna lista trovata. Prova un altro nome."
                  : scope === "mine"
                    ? "Non hai ancora creato liste. Inizia con Nuova lista."
                    : scope === "following"
                      ? "Le liste pubbliche che segui compariranno qui."
                      : "Non ci sono ancora liste pubbliche di altri utenti."}
              </p>
            </div>
          )}
          <ListPagination {...result.data} onChange={setOffset} />
        </>
      )}
    </section>
  );
}
