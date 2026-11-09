import { useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../ui/dialog";
import { type CommunityList, type ListInput } from "@/lib/community";
import { useCommunityMutation } from "@/lib/use-community";

export function ListForm({
  list,
  onClose,
  onSave,
}: {
  list?: CommunityList;
  onClose: () => void;
  onSave: (input: ListInput) => Promise<unknown>;
}) {
  const [name, setName] = useState(list?.name ?? "");
  const [description, setDescription] = useState(list?.description ?? "");
  const mutation = useCommunityMutation();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    if (
      await mutation.run(() =>
        onSave({
          name: name.trim(),
          description: description.trim(),
          is_public: list?.is_public ?? false,
        }),
      )
    )
      onClose();
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !mutation.busy) onClose();
      }}
    >
      <DialogContent className="community-dialog">
        <DialogTitle>{list ? "Modifica lista" : "Nuova lista"}</DialogTitle>
        <DialogDescription>
          {list
            ? "Aggiorna il nome e la descrizione."
            : "Raccogli i tuoi titoli. La lista nasce privata."}
        </DialogDescription>
        <form onSubmit={submit} className="community-form">
          <label htmlFor="list-name">Nome</label>
          <Input
            autoFocus
            id="list-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            required
            disabled={mutation.busy}
          />
          <label htmlFor="list-description">
            Descrizione <span>(facoltativa)</span>
          </label>
          <textarea
            id="list-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
            maxLength={2000}
            disabled={mutation.busy}
          />
          {mutation.error && (
            <p role="alert" className="community-error">
              {mutation.error}
            </p>
          )}
          <div className="community-actions">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={mutation.busy}
            >
              Annulla
            </Button>
            <Button type="submit" disabled={!name.trim() || mutation.busy}>
              {mutation.busy
                ? "Salvataggio…"
                : list
                  ? "Salva modifiche"
                  : "Crea lista"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
