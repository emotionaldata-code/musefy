import { Bookmark, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type Collection, type Title } from "@/lib/api";
import { useLibrary } from "@/lib/use-library";

export function TitleActions({
  title,
  variant = "detail",
}: {
  title: Title;
  variant?: "detail" | "compact";
}) {
  const library = useLibrary();
  const state = library.state(title);
  const pending = Boolean(library.pending[title.id]);
  const error = library.errors[title.id];
  const watchedLabel =
    title.source_type === "manga" ? "Già letto" : "Già visto";
  const actions: {
    collection: Collection;
    label: string;
    Icon: typeof Check;
  }[] = [
    { collection: "watched", label: watchedLabel, Icon: Check },
    { collection: "wishlist", label: "Wishlist", Icon: Bookmark },
  ];
  return (
    <div
      className="title-actions-block"
      data-variant={variant}
      data-busy={pending}
      data-error={Boolean(error)}
    >
      <div
        className="title-actions"
        role="group"
        aria-label={`La tua lista: ${title.title}`}
        aria-busy={pending}
      >
        {actions.map(({ collection, label, Icon }) => (
          <Button
            key={collection}
            variant="outline"
            size={variant === "compact" ? "icon" : "default"}
            className="title-action"
            aria-label={`${label}: ${title.title}`}
            aria-pressed={state[collection]}
            disabled={pending}
            title={`${state[collection] ? "Rimuovi da" : "Aggiungi a"} ${collection === "wishlist" ? "Guarda più tardi" : watchedLabel}`}
            onClick={() => void library.toggle(title, collection)}
          >
            <Icon aria-hidden="true" size={15} />
            <span className={variant === "compact" ? "sr-only" : undefined}>
              {label}
            </span>
          </Button>
        ))}
      </div>
      {error && (
        <p className="title-action-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
