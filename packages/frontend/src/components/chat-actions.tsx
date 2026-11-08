import { Button } from "@/components/ui/button";

export function ChatActions({
  pending,
  hasMore,
  more,
  edit,
  reset,
}: {
  pending: boolean;
  hasMore: boolean;
  more: () => void;
  edit: () => void;
  reset: () => void;
}) {
  return (
    <div
      role="group"
      aria-label="Continua la ricerca"
      className="mx-auto grid w-full max-w-180 shrink-0 grid-cols-2 gap-2 pt-3 sm:flex sm:flex-wrap sm:pt-4"
    >
      {hasMore && (
        <Button
          className="col-span-2 min-h-11"
          disabled={pending}
          onClick={more}
        >
          Altri consigli
        </Button>
      )}
      <Button
        variant="secondary"
        className="min-h-11 px-3"
        disabled={pending}
        onClick={edit}
      >
        Modifica descrizione
      </Button>
      <Button variant="ghost" className="min-h-11 px-3" onClick={reset}>
        Nuova ricerca
      </Button>
    </div>
  );
}
