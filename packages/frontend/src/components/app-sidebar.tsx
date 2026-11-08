import {
  BookOpen,
  Bookmark,
  Check,
  Clapperboard,
  ExternalLink,
  Film,
  Layers,
  MessageCircle,
  Tv,
  X,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Brand } from "@/components/brand";
import {
  categories,
  docsURL,
  type AppView,
  type Collection,
  type CatalogQuery,
  type Facets,
} from "@/lib/api";

const icons = [Layers, Film, Tv, Clapperboard, BookOpen];

function NavigationItem({
  active,
  Icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  Icon: LucideIcon;
  label: string;
  count?: number | null;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      className={`nav-item ${active ? "active" : ""}`}
      aria-current={active ? "page" : undefined}
      onClick={onClick}
    >
      <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
      <span>{label}</span>
      {count !== undefined && (
        <span className="nav-count">{count?.toLocaleString("it-IT") ?? "—"}</span>
      )}
    </Button>
  );
}

type SidebarProps = {
  view: AppView;
  query: CatalogQuery;
  facets: Facets | null;
  onNavigate: (type: string | null) => void;
  onCollection: (collection: Collection) => void;
  onClose?: () => void;
};

export function SidebarContent({
  view,
  query,
  facets,
  onNavigate,
  onCollection,
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
          <Brand />
        </a>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Chiudi menu"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain">
        <nav className="sidebar-nav" aria-label="Navigazione principale">
          <NavigationItem
            active={view === "chat"}
            Icon={MessageCircle}
            label="Musefy"
            onClick={() => onNavigate(null)}
          />
          <div className="nav-label">Esplora il catalogo</div>
          {categories.map((category, index) => {
            const Icon = icons[index];
            const active =
              view === "catalog" && query.source_type === category.value;
            const count = category.value
              ? (facets?.counts[category.value] ?? 0)
              : total;
            return (
              <NavigationItem
                key={category.value}
                active={active}
                Icon={Icon}
                label={category.label}
                count={facets ? count : null}
                onClick={() => onNavigate(category.value)}
              />
            );
          })}
        </nav>
        <nav
          className="sidebar-nav sidebar-library"
          aria-label="I tuoi elenchi"
        >
          <div className="nav-label">La tua biblioteca</div>
          {(
            [
              { value: "wishlist", label: "Guarda più tardi", Icon: Bookmark },
              { value: "watched", label: "Già visti", Icon: Check },
            ] as const
          ).map(({ value, label, Icon }) => (
            <NavigationItem
              key={value}
              active={view === value}
              Icon={Icon}
              label={label}
              onClick={() => onCollection(value)}
            />
          ))}
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
    <details className="attribution">
      <summary>Fonti e crediti</summary>
      <div className="attribution-content">
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
    </details>
  );
}
