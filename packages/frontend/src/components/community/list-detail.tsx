import { useState } from "react";
import type { TitlePage } from "@/lib/api";
import {
  type CommunityList,
  communityRequest,
  listPath,
  pagedPath,
  saveList,
} from "@/lib/community";
import {
  useCommunityMutation,
  useCommunityResource,
} from "@/lib/use-community";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../ui/dialog";
import { TitleCard } from "../title-card";
import { ListForm } from "./list-form";
import { CommunityStatus, ListPagination } from "./list-index";
import { ListShare } from "./list-share";
import { TitleSearch } from "./title-search";

export function CommunityListDetail({
  id,
  shareToken,
  onBack,
}: {
  id: string;
  shareToken: string | null;
  onBack: () => void;
}) {
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [adding, setAdding] = useState(false);
  const list = useCommunityResource<CommunityList>(
    listPath(id, "", shareToken),
    revision,
  );
  const mutation = useCommunityMutation();
  function refresh() {
    setRevision((value) => value + 1);
  }
  const data = list.data;
  return (
    <div className="community-page" data-ui>
      <Button className="community-back" variant="ghost" onClick={onBack}>
        ← Torna alle liste
      </Button>
      {!data && list.loading && (
        <p role="status" className="community-note">
          Caricamento lista…
        </p>
      )}
      {list.error && <CommunityStatus error={list.error} retry={refresh} />}
      {data && (
        <>
          <div className="community-detail-heading">
            <div>
              <h2>{data.name}</h2>
              <p className="community-note">
                di {data.owner.name ?? "un utente Musefy"} ·{" "}
                {data.is_public ? "Pubblica" : "Privata"} ·{" "}
                {data.follower_count} follower
              </p>
            </div>
            <div className="community-actions">
              {data.is_owner ? (
                <>
                  <Button onClick={() => setAdding(true)}>
                    Aggiungi titoli
                  </Button>
                  <Button variant="outline" onClick={() => setEditing(true)}>
                    Modifica
                  </Button>
                  <Button
                    variant="outline"
                    aria-pressed={data.is_public}
                    disabled={mutation.busy}
                    onClick={async () => {
                      if (
                        await mutation.run(() =>
                          saveList(listPath(id), "PUT", {
                            name: data.name,
                            description: data.description,
                            is_public: !data.is_public,
                          }),
                        )
                      )
                        refresh();
                    }}
                  >
                    {data.is_public ? "Rendi privata" : "Pubblica"}
                  </Button>
                </>
              ) : (
                data.is_public && (
                  <Button
                    variant={data.is_following ? "outline" : "default"}
                    aria-pressed={data.is_following}
                    disabled={mutation.busy}
                    onClick={async () => {
                      if (
                        await mutation.run(() =>
                          communityRequest(listPath(id, "/follow"), {
                            method: data.is_following ? "DELETE" : "PUT",
                          }),
                        )
                      )
                        refresh();
                    }}
                  >
                    {data.is_following ? "Non seguire più" : "Segui lista"}
                  </Button>
                )
              )}
            </div>
          </div>
          {data.description && (
            <p className="community-description">{data.description}</p>
          )}
          {!data.is_owner && !data.is_public && (
            <p className="community-note">
              Questa lista privata è condivisa con te in sola lettura.
            </p>
          )}
          <ListShare
            id={id}
            name={data.name}
            owner={data.is_owner}
            isPublic={data.is_public}
            shareToken={shareToken}
          />
          {mutation.error && (
            <p role="alert" className="community-error">
              {mutation.error}
            </p>
          )}
          <ListTitles
            key={id}
            id={id}
            shareToken={shareToken}
            owner={data.is_owner}
            revision={revision}
            onChanged={refresh}
          />
          {data.is_owner && (
            <div className="community-danger-zone">
              <Button
                variant="ghost"
                className="community-delete"
                onClick={() => setDeleting(true)}
              >
                Elimina lista
              </Button>
            </div>
          )}
          {editing && (
            <ListForm
              list={data}
              onClose={() => setEditing(false)}
              onSave={async (input) => {
                await saveList(listPath(id), "PUT", input);
                refresh();
              }}
            />
          )}
          {adding && (
            <TitleSearch
              listId={id}
              onClose={() => setAdding(false)}
              onAdded={refresh}
            />
          )}
          {deleting && (
            <Dialog
              open
              onOpenChange={(open) => {
                if (!open && !mutation.busy) setDeleting(false);
              }}
            >
              <DialogContent className="community-dialog">
                <DialogTitle>Eliminare questa lista?</DialogTitle>
                <DialogDescription>
                  La lista “{data.name}” e il suo link condiviso verranno
                  eliminati. I titoli restano nel catalogo.
                </DialogDescription>
                {mutation.error && (
                  <p role="alert" className="community-error">
                    {mutation.error}
                  </p>
                )}
                <div className="community-actions">
                  <Button
                    variant="outline"
                    disabled={mutation.busy}
                    onClick={() => setDeleting(false)}
                  >
                    Annulla
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={mutation.busy}
                    onClick={async () => {
                      if (
                        await mutation.run(() =>
                          communityRequest(listPath(id), { method: "DELETE" }),
                        )
                      )
                        onBack();
                    }}
                  >
                    {mutation.busy
                      ? "Eliminazione…"
                      : "Elimina definitivamente"}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          )}
        </>
      )}
    </div>
  );
}

function ListTitles({
  id,
  shareToken,
  owner,
  revision,
  onChanged,
}: {
  id: string;
  shareToken: string | null;
  owner: boolean;
  revision: number;
  onChanged: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const result = useCommunityResource<TitlePage>(
    pagedPath(listPath(id, "/items", shareToken), "", offset),
    revision + retry,
  );
  const mutation = useCommunityMutation();
  return (
    <section className="community-section" aria-label="Titoli della lista">
      <h3 className="community-section-title">
        Titoli {result.data && <span>{result.data.total}</span>}
      </h3>
      {result.loading && !result.data && (
        <p role="status" className="community-note">
          Caricamento titoli…
        </p>
      )}
      {result.error && (
        <CommunityStatus
          error={result.error}
          retry={() => setRetry((value) => value + 1)}
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
            <div className="community-empty">
              <p>
                {owner
                  ? "La lista è vuota. Scegli Aggiungi titoli per iniziare."
                  : "Questa lista non contiene ancora titoli."}
              </p>
            </div>
          )}
          <div className="catalog-grid">
            {result.data.items.map((title) => (
              <div className="community-title" key={title.id}>
                <TitleCard title={title} />
                {owner && (
                  <Button
                    variant="ghost"
                    className="community-remove"
                    disabled={mutation.busy}
                    aria-label={`Rimuovi dalla lista: ${title.title}`}
                    onClick={async () => {
                      if (
                        await mutation.run(() =>
                          communityRequest(listPath(id, `/items/${title.id}`), {
                            method: "DELETE",
                          }),
                        )
                      ) {
                        if (result.data?.items.length === 1 && offset > 0)
                          setOffset(Math.max(0, offset - result.data.limit));
                        onChanged();
                      }
                    }}
                  >
                    Rimuovi dalla lista
                  </Button>
                )}
              </div>
            ))}
          </div>
          <ListPagination {...result.data} onChange={setOffset} />
        </>
      )}
    </section>
  );
}
