import { useState } from "react";
import {
  communityRequest,
  listPath,
  sharedListURL,
  type ListShareResponse,
} from "@/lib/community";
import { useCommunityMutation } from "@/lib/use-community";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

export function ListShare({
  id,
  name,
  owner,
  isPublic,
  shareToken,
}: {
  id: string;
  name: string;
  owner: boolean;
  isPublic: boolean;
  shareToken: string | null;
}) {
  const [link, setLink] = useState("");
  const [notice, setNotice] = useState("");
  const mutation = useCommunityMutation();
  async function share() {
    setNotice("");
    await mutation.run(async () => {
      let token = isPublic ? null : shareToken;
      if (owner) {
        const created = await communityRequest<ListShareResponse>(
          listPath(id, "/share"),
          { method: "POST" },
        );
        token = created.token;
      }
      const url = sharedListURL(id, token);
      setLink(url);
      if (navigator.share) {
        try {
          await navigator.share({ title: name, url });
          setNotice("Link condiviso.");
          return;
        } catch (error) {
          if (error instanceof DOMException && error.name === "AbortError")
            return;
        }
      }
      try {
        await navigator.clipboard.writeText(url);
        setNotice(
          "Link copiato. Chi lo riceve può leggere la lista dopo l’accesso.",
        );
      } catch {
        throw new Error(
          "Copia automatica non disponibile. Seleziona e copia il link qui sotto.",
        );
      }
    });
  }
  return (
    <div className="community-share">
      <div className="community-actions">
        <Button variant="outline" onClick={share} disabled={mutation.busy}>
          {mutation.busy ? "Preparazione…" : "Condividi"}
        </Button>
        {owner && (
          <Button
            variant="ghost"
            disabled={mutation.busy}
            onClick={async () => {
              setNotice("");
              if (
                await mutation.run(() =>
                  communityRequest(listPath(id, "/share"), {
                    method: "DELETE",
                  }),
                )
              ) {
                setLink("");
                setNotice(
                  isPublic
                    ? "Link revocato. La lista pubblica resta visibile in Scopri liste."
                    : "Link revocato. La lista privata non è più leggibile dai link precedenti.",
                );
              }
            }}
          >
            Revoca link
          </Button>
        )}
      </div>
      {link && (
        <div className="community-share-link">
          <label htmlFor="list-share-url">Link di lettura</label>
          <Input
            id="list-share-url"
            readOnly
            value={link}
            onFocus={(event) => event.target.select()}
          />
          <p>
            {isPublic
              ? "Chi riceve il link può leggere la lista dopo l’accesso a Musefy."
              : "Chi ha questo link può leggere la lista privata dopo l’accesso a Musefy."}
          </p>
        </div>
      )}
      {notice && (
        <p role="status" className="community-note">
          {notice}
        </p>
      )}
      {mutation.error && (
        <p role="alert" className="community-error">
          {mutation.error}
        </p>
      )}
    </div>
  );
}
