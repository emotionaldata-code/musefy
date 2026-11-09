import { RefreshCw, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { categories, type CatalogQuery, type Facets } from "@/lib/api";
import "./catalog-toolbar.css";

interface FilterOption {
  value: string;
  label: string;
}

function CatalogFilter({
  label,
  allLabel,
  value,
  options,
  onChange,
}: {
  label: string;
  allLabel: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
}) {
  return (
    <Select
      value={value || "all"}
      onValueChange={(next) => onChange(next === "all" ? "" : next)}
    >
      <SelectTrigger
        aria-label={label}
        title={options.find((option) => option.value === value)?.label ?? label}
        data-filtered={Boolean(value)}
        className="catalog-filter"
      >
        <SelectValue>
          {options.find((option) => option.value === value)?.label ?? label}
        </SelectValue>
      </SelectTrigger>
      <SelectContent
        position="popper"
        align="start"
        sideOffset={6}
        className="max-h-80"
      >
        <SelectGroup>
          <SelectItem value="all" className="min-h-11 px-3 pr-8 text-sm">
            {allLabel}
          </SelectItem>
          {options.map((option) => (
            <SelectItem
              key={option.value}
              value={option.value}
              className="min-h-11 px-3 pr-8 text-sm"
            >
              {option.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

export function CatalogToolbar({
  query,
  search,
  facets,
  onSearch,
  onFilter,
  onRefresh,
}: {
  query: CatalogQuery;
  search: string;
  facets: Facets | null;
  onSearch: (value: string) => void;
  onFilter: (patch: Partial<CatalogQuery>) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="catalog-toolbar" role="search" aria-label="Cerca nel catalogo">
      <div className="catalog-search-row">
        <div className="catalog-search">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3.5 size-4 text-muted-foreground"
          />
          <label className="sr-only" htmlFor="search">
            Cerca un titolo
          </label>
          <Input
            id="search"
            type="search"
            placeholder="Cerca un titolo…"
            value={search}
            maxLength={200}
            onChange={(event) => onSearch(event.target.value)}
            className="catalog-search-input"
          />
          {search && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1"
              aria-label="Cancella ricerca"
              onClick={() => onSearch("")}
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onRefresh}
          aria-label="Aggiorna catalogo"
          title="Aggiorna catalogo"
        >
          <RefreshCw aria-hidden="true" />
        </Button>
      </div>
      <div className="catalog-formats" role="group" aria-label="Formato nel catalogo">
        {categories.map(({ value, label }) => (
          <Button
            key={value}
            variant="ghost"
            className="catalog-format"
            aria-pressed={query.source_type === value}
            onClick={() => onFilter({ source_type: value })}
          >
            {value ? label : "Tutti"}
          </Button>
        ))}
      </div>
      <div className="catalog-filters">
        <CatalogFilter
          label="Fonte"
          allLabel="Tutte le fonti"
          value={query.source}
          options={[
            { value: "tmdb", label: "TMDB" },
            { value: "jikan", label: "Jikan" },
          ]}
          onChange={(source) => onFilter({ source })}
        />
        <CatalogFilter
          label="Anno"
          allLabel="Tutti gli anni"
          value={query.year}
          options={(facets?.years ?? []).map((year) => ({
            value: String(year),
            label: String(year),
          }))}
          onChange={(year) => onFilter({ year })}
        />
        <CatalogFilter
          label="Genere"
          allLabel="Tutti i generi"
          value={query.genre}
          options={(facets?.genres ?? []).map((genre) => ({
            value: genre,
            label: genre,
          }))}
          onChange={(genre) => onFilter({ genre })}
        />
      </div>
    </div>
  );
}
