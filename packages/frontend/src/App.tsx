import { useEffect, useState } from "react";
import {
  BookOpen,
  Clapperboard,
  Film,
  Layers,
  Tv,
  X,
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CatalogToolbar } from "@/components/catalog-toolbar";
import { Skeleton } from "@/components/ui/skeleton";
import { TitleCard } from "@/components/title-card";
import { TitleDetail } from "@/components/title-detail";
import {
  categories,
  pageSize,
  titlesPath,
  type CatalogQuery,
  type Facets,
  type TitlePage,
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
  offset: Math.max(0, Number(initialParams.get("offset")) || 0),
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
  const { data, loading, error } = useResource<TitlePage>(
    titlesPath(query),
    revision,
  );
  const { data: facets } = useResource<Facets>("/titles/facets", revision);
  const total = Object.values(facets?.counts ?? {}).reduce(
    (sum, count) => sum + (count ?? 0),
    0,
  );
  const filtered = !!(query.q || query.source || query.year || query.genre);
  const heading =
    categories.find((category) => category.value === query.source_type)
      ?.label ?? "Catalogo";

  function update(patch: Partial<CatalogQuery>) {
    setQuery((current) => ({
      ...current,
      ...patch,
      offset: patch.offset ?? 0,
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
      offset: 0,
    });
  }
  useEffect(() => {
    const timer = window.setTimeout(
      () =>
        setQuery((current) =>
          current.q === search ? current : { ...current, q: search, offset: 0 },
        ),
      300,
    );
    return () => window.clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== "" && value !== 0) params.set(key, String(value));
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
          <p>Storie, in ogni formato.</p>
          <span>Metadati da TMDB e Jikan.</span>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
            Esplora le API <ExternalLink size={12} />
          </a>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span className="breadcrumb">
            Biblioteca <span>/</span> Catalogo
          </span>
          <span className="local-label">Archivio locale · sola lettura</span>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <h1>{heading}</h1>
              <p>
                Dal grande schermo alla pagina. Tutte le storie che hai
                raccolto.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => setRevision((value) => value + 1)}
              aria-label="Aggiorna catalogo"
            >
              <RefreshCw size={14} />
              <span>Aggiorna</span>
            </Button>
          </div>
          <CatalogToolbar
            query={query}
            search={search}
            facets={facets}
            onSearch={setSearch}
            onFilter={update}
          />
          <div className="results-line" aria-live="polite">
            <span>
              {loading
                ? "Caricamento…"
                : `${data?.total ?? 0} titoli${filtered ? " trovati" : " nel catalogo"}`}
            </span>
            {filtered && (
              <button onClick={reset}>
                Rimuovi filtri <X size={12} />
              </button>
            )}
            <span className="sort-label">Ordine di acquisizione</span>
          </div>
          {error ? (
            <div className="empty-state" role="alert">
              <h2>Il catalogo non è raggiungibile</h2>
              <p>{error}</p>
              <Button onClick={() => setRevision((value) => value + 1)}>
                Riprova
              </Button>
            </div>
          ) : loading ? (
            <div className="catalog-grid" aria-label="Caricamento catalogo">
              {Array.from({ length: 10 }, (_, index) => (
                <div key={index}>
                  <Skeleton className="aspect-[2/3] w-full rounded-lg" />
                  <Skeleton className="mt-3 h-4 w-3/4" />
                </div>
              ))}
            </div>
          ) : data?.items.length ? (
            <>
              <div className="catalog-grid">
                {data.items.map((title) => (
                  <TitleCard key={title.id} title={title} />
                ))}
              </div>
              <div className="pagination">
                <span>
                  {query.offset + 1}–{query.offset + data.items.length} di{" "}
                  {data.total} titoli
                </span>
                <div>
                  <Button
                    variant="outline"
                    aria-label="Pagina precedente"
                    disabled={!query.offset}
                    onClick={() =>
                      update({ offset: Math.max(0, query.offset - pageSize) })
                    }
                  >
                    <ArrowLeft size={14} />
                    Precedente
                  </Button>
                  <Button
                    variant="outline"
                    aria-label="Pagina successiva"
                    disabled={query.offset + pageSize >= data.total}
                    onClick={() => update({ offset: query.offset + pageSize })}
                  >
                    Successiva
                    <ArrowRight size={14} />
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <h2>
                {filtered || query.source_type
                  ? "Nessun titolo trovato"
                  : "La biblioteca è ancora vuota"}
              </h2>
              <p>
                {filtered || query.source_type
                  ? "Prova un altro titolo o modifica i filtri."
                  : "Le opere importate compariranno qui."}
              </p>
              {(filtered || query.source_type) && (
                <Button variant="outline" onClick={reset}>
                  Mostra tutti i titoli
                </Button>
              )}
            </div>
          )}
          <footer>
            <span>Musefy · Un archivio di storie</span>
            <span>
              This product uses the TMDB API but is not endorsed or certified by
              TMDB. Dati MAL tramite Jikan.
            </span>
          </footer>
        </main>
      </div>
      <TitleDetail key={id ?? "closed"} id={id} close={close} />
    </div>
  );
}
