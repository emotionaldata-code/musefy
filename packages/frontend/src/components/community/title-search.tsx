import { useState } from "react";
import { categoryName, type TitlePage } from "@/lib/api";
import { communityRequest, listPath, pagedPath } from "@/lib/community";
import {
  useCommunityMutation,
  useCommunityResource,
  useCommunitySearch,
} from "@/lib/use-community";
import { Poster } from "../title-card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../ui/dialog";
import { CommunityStatus, ListPagination } from "./list-index";

export function TitleSearch({
  listId,
  onClose,
  onAdded,
}: {
  listId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [search, setSearch] = useState("");
  const query = useCommunitySearch(search);
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="community-dialog community-search-dialog">
        <DialogTitle>Aggiungi titoli</DialogTitle>
        <DialogDescription>
          Cerca nel catalogo e aggiungi i titoli alla lista.
        </DialogDescription>
        <Input
          autoFocus
          type="search"
          aria-label="Cerca titoli da aggiungere"
          placeholder="Cerca un titolo"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {query ? (
          <SearchResults
            key={query}
            query={query}
            listId={listId}
            onAdded={onAdded}
          />
        ) : (
          <p className="community-note">
            Scrivi il nome di un film, una serie, un anime o un manga.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SearchResults({
  query,
  listId,
  onAdded,
}: {
  query: string;
  listId: string;
  onAdded: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [added, setAdded] = useState<number[]>([]);
  const result = useCommunityResource<TitlePage>(
    pagedPath("/titles", query, offset),
    revision,
  );
  const mutation = useCommunityMutation();
  return (
    <div className="community-search-results">
      {result.loading && <p role="status">Ricerca in corso…</p>}
      {result.error && (
        <CommunityStatus
          error={result.error}
          retry={() => setRevision((value) => value + 1)}
        />
      )}
      {mutation.error && (
        <p role="alert" className="community-error">
          {mutation.error}
        </p>
      )}
      {result.data && (
        <>
          {!result.data.items.length && (
            <p>Nessun titolo trovato. Prova un altro nome.</p>
          )}
          {result.data.items.map((title) => (
            <div className="community-search-row" key={title.id}>
              <Poster title={title} />
              <div>
                <p>{title.title}</p>
                <span>
                  {[title.year, categoryName(title.source_type)]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
              <Button
                variant="outline"
                disabled={mutation.busy || added.includes(title.id)}
                aria-label={`${added.includes(title.id) ? "Aggiunto" : "Aggiungi"}: ${title.title}`}
                onClick={async () => {
                  if (
                    await mutation.run(() =>
                      communityRequest(listPath(listId, `/items/${title.id}`), {
                        method: "PUT",
                      }),
                    )
                  ) {
                    setAdded((items) => [...items, title.id]);
                    onAdded();
                  }
                }}
              >
                {added.includes(title.id) ? "Aggiunto" : "Aggiungi"}
              </Button>
            </div>
          ))}
          <ListPagination {...result.data} onChange={setOffset} />
        </>
      )}
    </div>
  );
}
