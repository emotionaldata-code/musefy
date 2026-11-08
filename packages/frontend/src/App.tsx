import { useEffect, useState } from "react";
import {
  BookOpen,
  Clapperboard,
  Film,
  Layers,
  Tv,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CatalogToolbar } from "@/components/catalog-toolbar";
import { CatalogResults } from "@/components/catalog-results";
import { ThemeToggle } from "@/components/theme-toggle";
import { TitleDetail } from "@/components/title-detail";
import {
  categories,
  docsURL,
  titlesPath,
  type CatalogQuery,
  type Facets,
} from "@/lib/api";
import { useResource } from "@/lib/use-resource";

const icons = [Layers, Film, Tv, Clapperboard, BookOpen];
const initialParams = new URLSearchParams(window.location.search);
const initialQuery: CatalogQuery = {
  q: initialParams.get("q") ?? "",
  source: initialParams.get("source") ?? "",
  source_type: initialParams.get("source_type") ?? "",
  year: initialParams.get("year") ?? "",
  genre: initialParams.get("genre") ?? "",
};
function selectedId(): number | null {
  const match = /^#title\/(\d+)$/.exec(window.location.hash);
  return match ? Number(match[1]) : null;
}

export default function App() {
  const [query, setQuery] = useState(initialQuery);
  const [search, setSearch] = useState(initialQuery.q);
  const [revision, setRevision] = useState(0);
  const [id, setId] = useState(selectedId);
  const { data: facets } = useResource<Facets>("/titles/facets", revision);
  const total = Object.values(facets?.counts ?? {}).reduce(
    (sum, count) => sum + (count ?? 0),
    0,
  );
  const heading =
    categories.find((category) => category.value === query.source_type)
      ?.label ?? "Catalogo";

  function update(patch: Partial<CatalogQuery>) {
    setQuery((current) => ({
      ...current,
      ...patch,
    }));
  }
  function reset() {
    setSearch("");
    setQuery({
      ...initialQuery,
      q: "",
      source: "",
      source_type: "",
      year: "",
      genre: "",
    });
  }
  useEffect(() => {
    const timer = window.setTimeout(
      () =>
        setQuery((current) =>
          current.q === search ? current : { ...current, q: search },
        ),
      300,
    );
    return () => window.clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== "") params.set(key, String(value));
    });
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${params.size ? `?${params}` : ""}${window.location.hash}`,
    );
  }, [query]);
  useEffect(() => {
    const changed = () => setId(selectedId());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  function close() {
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}`,
    );
    setId(null);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand" aria-label="Musefy, catalogo">
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
        <div className="workspace">La tua biblioteca</div>
        <nav aria-label="Categorie del catalogo">
          {categories.map((category, index) => {
            const Icon = icons[index];
            const count = category.value
              ? (facets?.counts[category.value] ?? 0)
              : total;
            return (
              <button
                key={category.value}
                className={`nav-item ${query.source_type === category.value ? "active" : ""}`}
                aria-current={
                  query.source_type === category.value ? "page" : undefined
                }
                onClick={() => update({ source_type: category.value })}
              >
                <Icon size={18} strokeWidth={1.5} />
                <span>{category.label}</span>
                <span className="nav-count">{facets ? count : "—"}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <Attribution />
          <a href={docsURL} target="_blank" rel="noreferrer">
            API <ExternalLink size={12} />
          </a>
        </div>
      </aside>
      <div className="main-shell">
        <main>
          <div className="page-heading">
            <div>
              <h1>{heading}</h1>
            </div>
            <div className="heading-actions">
              <Button
                variant="ghost"
                size="icon"
                className="icon-button"
                onClick={() => setRevision((value) => value + 1)}
                aria-label="Aggiorna catalogo"
                title="Aggiorna catalogo"
              >
                <RefreshCw size={17} />
              </Button>
              <ThemeToggle />
            </div>
          </div>
          <CatalogToolbar
            query={query}
            search={search}
            facets={facets}
            onSearch={setSearch}
            onFilter={update}
          />
          <CatalogResults
            key={`${revision}:${titlesPath(query)}`}
            query={query}
            reset={reset}
          />
          <footer className="mobile-attribution">
            <Attribution />
          </footer>
        </main>
      </div>
      <TitleDetail key={id ?? "closed"} id={id} close={close} />
    </div>
  );
}

function Attribution() {
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
