import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TitleCredits } from "@/components/title-credits";
import { Skeleton } from "@/components/ui/skeleton";
import { categoryName, type Title } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import { Poster } from "./title-card";
import { TitleActions } from "./title-actions";

export function TitleDetail({
  id,
  close,
}: {
  id: number | null;
  close: () => void;
}) {
  const [revision, setRevision] = useState(0);
  const retry = () => setRevision((value) => value + 1);
  const {
    data: title,
    loading,
    error,
  } = useResource<Title>(id === null ? null : `/titles/${id}`, revision);
  const metadata = title?.metadata;
  const tags = [
    ...new Set([...(metadata?.themes ?? []), ...(metadata?.keywords ?? [])]),
  ];
  return (
    <Dialog
      open={id !== null}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent
        className="detail-dialog"
        aria-describedby="detail-description"
      >
        <ScrollArea
          className="detail-scroll"
          viewportProps={{
            "aria-label": "Contenuto della scheda",
            role: "region",
            tabIndex: 0,
          }}
        >
          <div className="detail-body">
            {loading || !title ? (
              <>
                <DialogTitle>
                  {error ? "Scheda non disponibile" : "Caricamento scheda"}
                </DialogTitle>
                <DialogDescription id="detail-description">
                  {error ?? "Lettura dei metadati dal catalogo."}
                </DialogDescription>
                {error ? (
                  <Button onClick={retry}>Riprova</Button>
                ) : (
                  <Skeleton className="h-60 w-full" />
                )}
              </>
            ) : (
              <>
                <div className="detail-intro">
                  <Poster title={title} />
                  <div className="detail-heading">
                    <div className="detail-meta">
                      {[title.year, categoryName(title.source_type)]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                    <DialogTitle>{title.title}</DialogTitle>
                    <DialogDescription
                      id="detail-description"
                      className={
                        metadata?.original_title &&
                        metadata.original_title !== title.title
                          ? ""
                          : "sr-only"
                      }
                    >
                      {metadata?.original_title &&
                      metadata.original_title !== title.title
                        ? metadata.original_title
                        : `Scheda di ${title.title}`}
                    </DialogDescription>
                    {!!title.genres?.length && (
                      <p className="detail-genres">
                        {title.genres.join(" · ")}
                      </p>
                    )}
                    <TitleActions title={title} />
                  </div>
                </div>
                {metadata?.synopsis && (
                  <section className="detail-section">
                    <h3>Sinossi</h3>
                    <p className="synopsis">{metadata.synopsis}</p>
                  </section>
                )}
                {!!(
                  (metadata?.staff.length ?? 0) + (metadata?.cast.length ?? 0)
                ) && (
                  <details className="detail-section disclosure">
                    <summary>Cast e autori</summary>
                    <div className="detail-columns">
                      <TitleCredits
                        heading="Autori e staff"
                        people={metadata?.staff ?? []}
                      />
                      <TitleCredits
                        heading="Cast e personaggi"
                        people={metadata?.cast ?? []}
                      />
                    </div>
                  </details>
                )}
                <details className="detail-section disclosure">
                  <summary>Altri dettagli</summary>
                  {!!metadata?.ratings.length && (
                    <div className="detail-ratings">
                      {metadata?.ratings.map((rating) => (
                        <div key={rating.source}>
                          <strong>
                            {rating.value.toFixed(1)}
                            <small> / {rating.scale}</small>
                          </strong>
                          <span>
                            {rating.source === "tmdb" ? "TMDB" : "MyAnimeList"}{" "}
                            {rating.votes != null &&
                              ` · ${rating.votes.toLocaleString("it-IT")} voti`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {!!tags.length && (
                    <section className="detail-section">
                      <h3>Temi e parole chiave</h3>
                      <p>{tags.join(" · ")}</p>
                    </section>
                  )}
                  {!!metadata?.studios.length && (
                    <section className="detail-section">
                      <h3>Studi e produzione</h3>
                      <p>{metadata.studios.join(" · ")}</p>
                    </section>
                  )}
                  {!!metadata?.relations.length && (
                    <section className="detail-section">
                      <h3>Opere collegate</h3>
                      <ul className="relation-list">
                        {metadata.relations.map((relation, index) => (
                          <li key={index}>
                            {relation.url ? (
                              <a
                                href={relation.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {relation.title ?? relation.source_id}
                                <ExternalLink size={12} />
                              </a>
                            ) : (
                              <span>
                                {relation.title ?? relation.source_id}
                              </span>
                            )}
                            <small>
                              {relation.relation} · {relation.source_type}
                            </small>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  <section className="detail-section provenance">
                    {!!metadata?.alternative_titles.length && (
                      <p>{metadata.alternative_titles.join(" · ")}</p>
                    )}
                    <p>
                      API:{" "}
                      {metadata?.api_base_url ??
                        (title.source === "tmdb"
                          ? "https://api.themoviedb.org/3"
                          : "Non registrata")}
                    </p>
                    <p>
                      Fonte: {title.source} · ID: {title.source_id} · Acquisito:{" "}
                      {new Date(title.fetched_at).toLocaleString("it-IT")}
                    </p>
                    <ul>
                      {metadata?.external_ids.map((external, index) => (
                        <li key={index}>
                          {external.namespace}: {external.value}
                        </li>
                      ))}
                    </ul>
                    <a
                      className="source-link"
                      href={title.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Pagina originale <ExternalLink size={14} />
                    </a>
                  </section>
                </details>
              </>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
