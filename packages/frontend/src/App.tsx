import { useEffect, useState } from "react";
import { PanelLeft } from "lucide-react";
import { Attribution, SidebarContent } from "@/components/app-sidebar";
import { useMobile } from "@/lib/use-mobile";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Chat } from "@/components/chat";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { CatalogToolbar } from "@/components/catalog-toolbar";
import { CatalogResults } from "@/components/catalog-results";
import { ThemeToggle } from "@/components/theme-toggle";
import { AccountMenu } from "@/components/account-menu";
import { Login } from "@/components/login";
import { useAuth } from "@/lib/use-auth";
import { TitleDetail } from "@/components/title-detail";
import {
  categories,
  titlesPath,
  type CatalogQuery,
  type Facets,
  type AppView,
  type Collection,
} from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import { LibraryProvider, useLibrary } from "@/lib/use-library";

const initialParams = new URLSearchParams(window.location.search);
initialParams.delete("auth_error");
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
  const auth = useAuth();
  if (auth.status !== "authenticated")
    return <Login status={auth.status} retry={auth.retry} />;
  return (
    <LibraryProvider key={auth.user.id}>
      <AuthenticatedApp auth={auth} />
    </LibraryProvider>
  );
}

function AuthenticatedApp({
  auth,
}: {
  auth: ReturnType<typeof useAuth> & { status: "authenticated" };
}) {
  const [view, setView] = useState<AppView>(
    initialParams.get("view") === "wishlist"
      ? "wishlist"
      : initialParams.get("view") === "watched"
        ? "watched"
        : initialParams.size || window.location.hash
          ? "catalog"
          : "chat",
  );
  const library = useLibrary();
  const collection =
    view === "watched" || view === "wishlist" ? view : undefined;
  const mobile = useMobile();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => {
    const closeMenu = () => setMobileOpen(false);
    window.addEventListener("resize", closeMenu);
    return () => window.removeEventListener("resize", closeMenu);
  }, []);
  const [query, setQuery] = useState(initialQuery);
  const [search, setSearch] = useState(initialQuery.q);
  const [revision, setRevision] = useState(0);
  const [id, setId] = useState(selectedId);
  const { data: facets } = useResource<Facets>("/titles/facets", revision);
  const heading =
    collection === "wishlist"
      ? "Guarda più tardi"
      : collection === "watched"
        ? "Già visti"
        : (categories.find((category) => category.value === query.source_type)
            ?.label ?? "Catalogo");

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
    if (view !== "chat") {
      params.set("view", view);
      Object.entries(query).forEach(([key, value]) => {
        if (value !== "") params.set(key, String(value));
      });
    }
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${params.size ? `?${params}` : ""}${window.location.hash}`,
    );
  }, [query, view]);
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

  function navigate(type: string | null) {
    setView(type === null ? "chat" : "catalog");
    if (type !== null) update({ source_type: type });
    setMobileOpen(false);
  }

  function navigateCollection(next: Collection) {
    reset();
    setView(next);
    setMobileOpen(false);
  }

  return (
    <Sheet open={mobile && mobileOpen} onOpenChange={setMobileOpen}>
      <Collapsible
        open={sidebarOpen}
        onOpenChange={setSidebarOpen}
        className={`app-shell ${!mobile && sidebarOpen ? "" : "sidebar-collapsed"}`}
      >
        {mobile ? (
          <SheetContent
            side="left"
            className="mobile-sidebar data-[side=left]:w-[min(20rem,calc(100vw-3rem))] gap-0 border-0 p-5 pt-[max(1.25rem,env(safe-area-inset-top))]"
            showCloseButton={false}
            aria-describedby={undefined}
          >
            <SheetTitle className="sr-only">Navigazione Musefy</SheetTitle>
            <SidebarContent
              view={view}
              query={query}
              facets={facets}
              onNavigate={navigate}
              onCollection={navigateCollection}
              onClose={() => setMobileOpen(false)}
            />
          </SheetContent>
        ) : (
          <CollapsibleContent asChild>
            <aside className="sidebar" id="app-sidebar">
              <SidebarContent
                view={view}
                query={query}
                facets={facets}
                onNavigate={navigate}
                onCollection={navigateCollection}
              />
            </aside>
          </CollapsibleContent>
        )}
        <div className="main-shell">
          <main className={view === "chat" ? "chat-page" : undefined}>
            <div className="page-heading">
              <div className="heading-title">
                {mobile ? (
                  <SheetTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Apri menu"
                      title="Apri menu"
                    >
                      <PanelLeft aria-hidden="true" />
                    </Button>
                  </SheetTrigger>
                ) : (
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={
                        sidebarOpen ? "Chiudi sidebar" : "Apri sidebar"
                      }
                      title={sidebarOpen ? "Chiudi sidebar" : "Apri sidebar"}
                    >
                      <PanelLeft aria-hidden="true" />
                    </Button>
                  </CollapsibleTrigger>
                )}
                <h1>{view === "chat" ? "Musefy" : heading}</h1>
              </div>
              <div className="heading-actions">
                <ThemeToggle />
                <AccountMenu
                  user={auth.user}
                  logout={auth.logout}
                  loggingOut={auth.loggingOut}
                  logoutError={auth.logoutError}
                />
              </div>
            </div>
            <Chat active={view === "chat"} />
            {view !== "chat" && (
              <>
                <CatalogToolbar
                  query={query}
                  search={search}
                  facets={facets}
                  onSearch={setSearch}
                  onFilter={update}
                  onRefresh={() => {
                    library.refresh();
                    setRevision((value) => value + 1);
                  }}
                />
                <CatalogResults
                  key={`${revision}:${collection ? library.revisions[collection] : 0}:${titlesPath(query, 0, collection)}`}
                  query={query}
                  collection={collection}
                  reset={reset}
                />
                <footer className="mobile-attribution">
                  <Attribution />
                </footer>
              </>
            )}
          </main>
        </div>
        <TitleDetail key={id ?? "closed"} id={id} close={close} />
      </Collapsible>
    </Sheet>
  );
}
