import {
  BookOpen,
  Clapperboard,
  ExternalLink,
  Film,
  Layers,
  MessageCircle,
  Tv,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { categories, docsURL, type CatalogQuery, type Facets } from "@/lib/api";

const icons = [Layers, Film, Tv, Clapperboard, BookOpen];

type SidebarProps = {
  view: "chat" | "catalog";
  query: CatalogQuery;
  facets: Facets | null;
  onNavigate: (type: string | null) => void;
  onClose?: () => void;
};

export function SidebarContent({
  view,
  query,
  facets,
  onNavigate,
  onClose,
}: SidebarProps) {
  const total = Object.values(facets?.counts ?? {}).reduce(
    (sum, count) => sum + (count ?? 0),
    0,
  );
  return (
    <>
      <div className="flex shrink-0 items-center justify-between gap-3">
        <a
          href="/"
          className="brand"
          aria-label="Musefy, chat"
          onClick={(event) => {
            event.preventDefault();
            onNavigate(null);
          }}
        >
          <svg viewBox="0 0 30 30" fill="none" aria-hidden="true">
            <path
              d="M3 24V6l12 12L27 6v18M3 6l12 12L27 6"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinejoin="round"
            />
          </svg>
          <span>
            musefy<span className="brand-period">.</span>
          </span>
        </a>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="icon-button"
            aria-label="Chiudi menu"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain">
        <div className="workspace">La tua biblioteca</div>
        <nav className="sidebar-nav" aria-label="Navigazione principale">
          <Button
            variant="ghost"
            className={`nav-item ${view === "chat" ? "active" : ""}`}
            aria-current={view === "chat" ? "page" : undefined}
            onClick={() => onNavigate(null)}
          >
            <MessageCircle size={18} strokeWidth={1.5} />
            <span>Musefy</span>
          </Button>
          {categories.map((category, index) => {
            const Icon = icons[index];
            const active =
              view === "catalog" && query.source_type === category.value;
            const count = category.value
              ? (facets?.counts[category.value] ?? 0)
              : total;
            return (
              <Button
                variant="ghost"
                key={category.value}
                className={`nav-item ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
                onClick={() => onNavigate(category.value)}
              >
                <Icon size={18} strokeWidth={1.5} />
                <span>{category.label}</span>
                <span className="nav-count">{facets ? count : "—"}</span>
              </Button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <Attribution />
          <a href={docsURL} target="_blank" rel="noreferrer">
            API <ExternalLink size={12} />
          </a>
        </div>
      </div>
    </>
  );
}

export function Attribution() {
  return (
    <div className="attribution">
      <p>
        Metadati:{" "}
        <a href="https://www.themoviedb.org/" target="_blank" rel="noreferrer">
          TMDB
        </a>{" "}
        e Jikan.
      </p>
      <p>
        This product uses the TMDB API but is not endorsed or certified by TMDB.
      </p>
      <p>Dati MyAnimeList tramite API compatibile Jikan.</p>
    </div>
  );
}
