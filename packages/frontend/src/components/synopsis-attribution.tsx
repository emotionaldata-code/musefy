import type { Title } from "@/lib/api";

export function SynopsisAttribution({
  enrichment,
}: {
  enrichment: Title["metadata"]["synopsis_enrichment"];
}) {
  if (!enrichment) return null;
  return (
    <p className="provenance text-xs">
      Sinossi:{" "}
      <a href={enrichment.url} target="_blank" rel="noreferrer">
        {enrichment.provider === "tvmaze" ? "TVmaze" : "TMDB"}
      </a>
      {enrichment.provider === "tvmaze" && (
        <>
          {" · "}
          <a
            href="https://creativecommons.org/licenses/by-sa/4.0/"
            target="_blank"
            rel="noreferrer"
          >
            CC BY-SA 4.0
          </a>
          {" · formattazione HTML rimossa"}
        </>
      )}
    </p>
  );
}
