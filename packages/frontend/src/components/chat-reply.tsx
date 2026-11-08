import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Poster } from "@/components/title-card";
import { categoryName } from "@/lib/api";
import type { Exchange, SearchHit } from "@/lib/use-recommendations";

function Recommendation({ hit }: { hit: SearchHit }) {
  const { title } = hit;
  return (
    <a
      href={`#title/${title.id}`}
      aria-label={`Apri ${title.title}`}
      className="recommendation group"
    >
      <Poster
        title={title}
        className="w-16 shrink-0 self-start sm:w-20"
      />
      <div className="min-w-0 py-0.5">
        <h3 className="font-semibold leading-snug [overflow-wrap:anywhere] group-hover:underline">
          {title.title}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {[categoryName(title.source_type), title.year]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {title.metadata.synopsis && (
          <p className="mt-2 line-clamp-3 text-sm leading-relaxed">
            {title.metadata.synopsis}
          </p>
        )}
      </div>
    </a>
  );
}

export function ChatReply({
  exchange,
  pending,
  retry,
}: {
  exchange: Exchange;
  pending: boolean;
  retry: (exchange: Exchange) => Promise<void>;
}) {
  const { reply } = exchange;
  if (reply.status === "loading")
    return (
      <p
        role="status"
        className="flex items-center gap-2 text-sm text-muted-foreground"
      >
        <LoaderCircle
          className="size-4 motion-safe:animate-spin"
          aria-hidden="true"
        />
        Cerco nel catalogo…
      </p>
    );
  if (reply.status === "error")
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm leading-relaxed">
          Non riesco a cercare ora. Riprova tra poco.
        </p>
        <Button
          variant="secondary"
          disabled={pending}
          onClick={() => void retry(exchange)}
        >
          Riprova la ricerca
        </Button>
      </div>
    );
  if (!reply.items.length)
    return (
      <p className="text-sm leading-relaxed">
        {exchange.offset
          ? "Non ci sono altri titoli per questa ricerca."
          : "Non ho trovato titoli per questa ricerca."}
      </p>
    );
  return (
    <div className="space-y-3">
      <p className="text-sm leading-relaxed">
        {reply.items.length === 1
          ? "Un titolo da provare:"
          : exchange.offset
            ? "Altri titoli da provare:"
            : "Due titoli da provare:"}
      </p>
      <div className="space-y-3" aria-label="Titoli consigliati">
        {reply.items.map((hit) => (
          <Recommendation key={hit.title.id} hit={hit} />
        ))}
      </div>
    </div>
  );
}
