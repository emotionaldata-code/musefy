import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
                      {categoryName(title.source_type)} ·{" "}
                      {title.year ?? "Anno non disponibile"} ·{" "}
                      {metadata?.format}
                    </div>
                    <DialogTitle>{title.title}</DialogTitle>
                    <DialogDescription id="detail-description">
                      {metadata?.original_title ?? title.title}
                    </DialogDescription>
                    <div className="tags">
                      {(title.genres ?? []).map((genre) => (
                        <Badge key={genre} variant="secondary">
                          {genre}
                        </Badge>
                      ))}
                    </div>
                    <div className="detail-ratings">
                      {metadata?.ratings.map((rating) => (
                        <div key={rating.source}>
                          <strong>
                            {rating.value.toFixed(1)}
                            <small> / {rating.scale}</small>
                          </strong>
                          <span>
                            {rating.source === "tmdb" ? "TMDB" : "MyAnimeList"}{" "}
                            · {rating.votes?.toLocaleString("it-IT") ?? "—"}{" "}
                            voti
                          </span>
                        </div>
                      ))}
                    </div>
                    <Button asChild variant="outline">
                      <a href={title.url} target="_blank" rel="noreferrer">
                        Apri su{" "}
                        {title.source === "tmdb" ? "TMDB" : "MyAnimeList"}
                        <ExternalLink size={14} />
                      </a>
                    </Button>
                  </div>
                </div>
                <section className="detail-section">
                  <h3>Sinossi</h3>
                  <p className="synopsis">
                    {metadata?.synopsis ??
                      "La fonte non fornisce una sinossi per questo titolo."}
                  </p>
                  {metadata?.synopsis_language && (
                    <small>
                      Lingua della sinossi: {metadata.synopsis_language}
                    </small>
                  )}
                </section>
                {!!(
                  (metadata?.keywords.length ?? 0) +
                  (metadata?.themes.length ?? 0)
                ) && (
                  <section className="detail-section">
                    <h3>Temi e parole chiave</h3>
                    <div className="tags">
                      {[
                        ...new Set([
                          ...(metadata?.themes ?? []),
                          ...(metadata?.keywords ?? []),
                        ]),
                      ].map((tag) => (
                        <Badge key={tag} variant="outline">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </section>
                )}
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
                            <span>{relation.title ?? relation.source_id}</span>
                          )}
                          <small>
                            {relation.relation} · {relation.source_type}
                          </small>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                <details className="detail-section provenance">
                  <summary>Titoli alternativi e provenienza</summary>
                  <p>
                    {metadata?.alternative_titles.join(" · ") ||
                      "Nessun titolo alternativo"}
                  </p>
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
                </details>
              </>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
