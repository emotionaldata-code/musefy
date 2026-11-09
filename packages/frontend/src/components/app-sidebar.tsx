import {
  Bookmark,
  Check,
  ExternalLink,
  Layers,
  List,
  Compass,
  MessageCircle,
  X,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Brand } from "@/components/brand";
import { docsURL, type AppView } from "@/lib/api";

function NavigationItem({
  active,
  Icon,
  label,
  onClick,
}: {
  active: boolean;
  Icon: LucideIcon;
  label: string;
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
    </Button>
  );
}

type SidebarProps = {
  view: AppView;
  onNavigate: (view: AppView) => void;
  onClose?: () => void;
};

export function SidebarContent({
  view,
  onNavigate,
  onClose,
}: SidebarProps) {
  return (
    <>
      <div className="flex shrink-0 items-center justify-between gap-3">
        <a
          href="/"
          className="brand"
          aria-label="Musefy, chat"
          onClick={(event) => {
            event.preventDefault();
            onNavigate("chat");
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
            onClick={() => onNavigate("chat")}
          />
          <div className="nav-label">Esplora il catalogo</div>
          <NavigationItem
            active={view === "catalog"}
            Icon={Layers}
            label="Esplora"
            onClick={() => onNavigate("catalog")}
          />
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
              onClick={() => onNavigate(value)}
            />
          ))}
        </nav>
        <nav className="sidebar-nav sidebar-library" aria-label="Community">
          <div className="nav-label">Community</div>
          <NavigationItem
            active={view === "lists"}
            Icon={List}
            label="Le tue liste"
            onClick={() => onNavigate("lists")}
          />
          <NavigationItem
            active={view === "discover"}
            Icon={Compass}
            label="Scopri liste"
            onClick={() => onNavigate("discover")}
          />
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
