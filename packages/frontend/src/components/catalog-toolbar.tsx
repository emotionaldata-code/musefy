import { Search, X } from "lucide-react";
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
import type { CatalogQuery, Facets } from "@/lib/api";

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
        title={value || label}
        className="h-11 w-full min-w-0 rounded-full bg-card px-3 text-[14px] text-foreground hover:bg-muted active:bg-muted data-[size=default]:h-11 max-sm:min-h-[44px] [&_[data-slot=select-value]]:block [&_[data-slot=select-value]]:truncate"
      >
        <SelectValue>
          {options.find((option) => option.value === value)?.label ?? label}
        </SelectValue>
      </SelectTrigger>
      <SelectContent
        position="popper"
        align="start"
        sideOffset={6}
        className="max-h-80 border border-border shadow-lg"
      >
        <SelectGroup>
          <SelectItem value="all" className="min-h-10 px-3 pr-8 text-[14px]">
            {allLabel}
          </SelectItem>
          {options.map((option) => (
            <SelectItem
              key={option.value}
              value={option.value}
              className="min-h-10 px-3 pr-8 text-[14px]"
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
}: {
  query: CatalogQuery;
  search: string;
  facets: Facets | null;
  onSearch: (value: string) => void;
  onFilter: (patch: Partial<CatalogQuery>) => void;
}) {
  return (
    <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between xl:gap-5">
      <div className="relative flex w-full items-center xl:max-w-80">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3.5 size-4 text-muted-foreground"
        />
        <label className="sr-only" htmlFor="search">
          Cerca un titolo
        </label>
        <Input
          id="search"
          placeholder="Cerca un titolo…"
          value={search}
          maxLength={200}
          onChange={(event) => onSearch(event.target.value)}
          className="h-11 rounded-full bg-card pr-11 pl-10 text-[16px] max-sm:min-h-[44px] md:text-[14px]"
        />
        {search && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="absolute right-1"
            aria-label="Cancella ricerca"
            onClick={() => onSearch("")}
          >
            <X className="size-4" />
          </Button>
        )}
      </div>
      <div className="grid min-w-0 grid-cols-3 gap-2 xl:w-[32rem] xl:shrink-0">
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
