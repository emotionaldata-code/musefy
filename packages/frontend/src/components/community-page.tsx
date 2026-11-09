import { useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { ListForm } from "./community/list-form";
import { ListIndex } from "./community/list-index";
import { CommunityListDetail } from "./community/list-detail";
import { saveList } from "@/lib/community";
import { useCommunitySearch } from "@/lib/use-community";
import "./community/community.css";

export function CommunityPage({
  view,
  userId,
  listId,
  shareToken,
  onSelect,
}: {
  view: "lists" | "discover";
  userId: number;
  listId: string | null;
  shareToken: string | null;
  onSelect: (id: string | null, shareToken?: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const query = useCommunitySearch(search);
  if (listId)
    return (
      <CommunityListDetail
        key={`${userId}:${listId}:${shareToken}`}
        id={listId}
        shareToken={shareToken}
        onBack={() => onSelect(null)}
      />
    );
  return (
    <div className="community-page" data-ui>
      <div className="community-toolbar">
        <Input
          type="search"
          aria-label="Cerca liste"
          placeholder="Cerca liste per nome o descrizione"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          maxLength={200}
        />
        {view === "lists" && (
          <Button onClick={() => setCreating(true)}>Nuova lista</Button>
        )}
      </div>
      <div key={`${view}:${query}`}>
        {view === "lists" ? (
          <>
            <ListIndex scope="mine" query={query} onSelect={onSelect} />
            <ListIndex scope="following" query={query} onSelect={onSelect} />
          </>
        ) : (
          <ListIndex scope="discover" query={query} onSelect={onSelect} />
        )}
      </div>
      {creating && (
        <ListForm
          onClose={() => setCreating(false)}
          onSave={async (input) => {
            const list = await saveList("/lists", "POST", input);
            setCreating(false);
            onSelect(list.id);
          }}
        />
      )}
    </div>
  );
}
