import { Bookmark, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type Collection, type Title } from "@/lib/api";
import { useLibrary } from "@/lib/use-library";

export function TitleActions({ title }: { title: Title }) {
  const library = useLibrary();
  const state = library.state(title);
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
    <div className="title-actions-block">
      <div
        className="title-actions"
        role="group"
        aria-label={`La tua lista: ${title.title}`}
      >
        {actions.map(({ collection, label, Icon }) => (
          <Button
            key={collection}
            variant="outline"
            className="title-action"
            aria-label={`${label}: ${title.title}`}
            aria-pressed={state[collection]}
            disabled={library.pending[title.id]}
            title={`${state[collection] ? "Rimuovi da" : "Aggiungi a"} ${collection === "wishlist" ? "Guarda più tardi" : watchedLabel}`}
            onClick={() => void library.toggle(title, collection)}
          >
            <Icon aria-hidden="true" size={15} />
            <span>{label}</span>
          </Button>
        ))}
      </div>
      {library.errors[title.id] && (
        <p className="title-action-error" role="alert">
          {library.errors[title.id]}
        </p>
      )}
    </div>
  );
}
