import { useEffect, useRef, useState } from "react";
import { Menu } from "lucide-react";
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
import { CommunityPage } from "@/components/community-page";
import { ThemeToggle } from "@/components/theme-toggle";
import { AccountMenu } from "@/components/account-menu";
import { Login } from "@/components/login";
import { useAuth } from "@/lib/use-auth";
import { TitleDetail } from "@/components/title-detail";
import {
  titlesPath,
  type CatalogQuery,
  type Facets,
  type AppView,
} from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import { LibraryProvider, useLibrary } from "@/lib/use-library";

const emptyQuery: CatalogQuery = {
  q: "",
  source: "",
  source_type: "",
  year: "",
  genre: "",
};

type Route = {
  view: AppView;
  listId: string | null;
  shareToken: string | null;
};

function readLocation(): { route: Route; query: CatalogQuery } {
  const params = new URLSearchParams(window.location.search);
  params.delete("auth_error");
  const requested = params.get("view");
  const view: AppView =
    requested === "chat" ||
    requested === "catalog" ||
    requested === "wishlist" ||
    requested === "watched" ||
    requested === "lists" ||
    requested === "discover"
      ? requested
      : params.size || window.location.hash
        ? "catalog"
        : "chat";
  const community = view === "lists" || view === "discover";
  return {
    route: {
      view,
      listId: community ? params.get("list") : null,
      shareToken: community ? params.get("share") : null,
    },
    query: {
      q: params.get("q") ?? "",
      source: params.get("source") ?? "",
      source_type: params.get("source_type") ?? "",
      year: params.get("year") ?? "",
      genre: params.get("genre") ?? "",
    },
  };
}

function routeURL(route: Route, query: CatalogQuery, hash = window.location.hash) {
  const params = new URLSearchParams();
  if (route.view !== "chat") {
    params.set("view", route.view);
    if (route.view === "lists" || route.view === "discover") {
      if (route.listId) params.set("list", route.listId);
      if (route.shareToken) params.set("share", route.shareToken);
    } else {
      Object.entries(query).forEach(([key, value]) => {
        if (value !== "") params.set(key, value);
      });
    }
  }
  return `${window.location.pathname}${params.size ? `?${params}` : ""}${hash}`;
}

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
  const [initial] = useState(readLocation);
  const [route, setRoute] = useState(initial.route);
  const locationPath = useRef(`${window.location.pathname}${window.location.search}`);
  const { view, listId, shareToken } = route;
  const community = view === "lists" || view === "discover";
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
  const [query, setQuery] = useState(initial.query);
  const [search, setSearch] = useState(initial.query.q);
  const [revision, setRevision] = useState(0);
  const [id, setId] = useState(selectedId);
  const { data: facets } = useResource<Facets>("/titles/facets", revision);
  const heading =
    view === "chat"
      ? "Musefy"
      : view === "wishlist"
        ? "Guarda più tardi"
        : view === "watched"
          ? "Già visti"
          : view === "lists"
            ? "Le tue liste"
            : view === "discover"
              ? "Scopri liste"
              : "Esplora";

  function update(patch: Partial<CatalogQuery>) {
    setQuery((current) => ({
      ...current,
      ...patch,
    }));
  }
  function reset() {
    setSearch("");
    setQuery(emptyQuery);
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
    window.history.replaceState(null, "", routeURL(route, query));
    locationPath.current = `${window.location.pathname}${window.location.search}`;
  }, [query, route]);
  useEffect(() => {
    const changed = () => {
      setId(selectedId());
      const path = `${window.location.pathname}${window.location.search}`;
      if (path === locationPath.current) return;
      locationPath.current = path;
      const next = readLocation();
      setRoute(next.route);
      setQuery(next.query);
      setSearch(next.query.q);
      setMobileOpen(false);
    };
    window.addEventListener("popstate", changed);
    return () => window.removeEventListener("popstate", changed);
  }, []);
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

  function navigate(next: AppView) {
    const nextRoute: Route = { view: next, listId: null, shareToken: null };
    const nextQuery =
      next === "wishlist" || next === "watched" ? emptyQuery : query;
    const url = routeURL(nextRoute, nextQuery, "");
    if (
      url !== `${window.location.pathname}${window.location.search}${window.location.hash}`
    ) window.history.pushState(null, "", url);
    if (nextQuery === emptyQuery) reset();
    setRoute(nextRoute);
    setId(null);
    setMobileOpen(false);
  }

  function selectList(nextId: string | null, token?: string) {
    const nextRoute = { ...route, listId: nextId, shareToken: token ?? null };
    const url = routeURL(nextRoute, query, "");
    if (
      url !== `${window.location.pathname}${window.location.search}${window.location.hash}`
    ) window.history.pushState(null, "", url);
    setRoute(nextRoute);
    setId(null);
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
              onNavigate={navigate}
              onClose={() => setMobileOpen(false)}
            />
          </SheetContent>
        ) : (
          <CollapsibleContent asChild>
            <aside className="sidebar" id="app-sidebar">
              <SidebarContent view={view} onNavigate={navigate} />
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
                      <Menu aria-hidden="true" />
                    </Button>
                  </SheetTrigger>
                ) : (
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={
                        sidebarOpen ? "Chiudi menu" : "Apri menu"
                      }
                      title={sidebarOpen ? "Chiudi menu" : "Apri menu"}
                    >
                      <Menu aria-hidden="true" />
                    </Button>
                  </CollapsibleTrigger>
                )}
                <h1>{heading}</h1>
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
            {community && (
              <CommunityPage
                view={view}
                userId={auth.user.id}
                listId={listId}
                shareToken={shareToken}
                onSelect={selectList}
              />
            )}
            {view !== "chat" && !community && (
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
