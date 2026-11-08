import { ImageOff } from "lucide-react";
import { useState } from "react";
import { categoryName, type Title } from "@/lib/api";
import { TitleActions } from "./title-actions";

export function Poster({
  title,
  className = "",
}: {
  title: Pick<Title, "title" | "metadata">;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const image = title.metadata.image_url;
  return (
    <div className={`poster ${className}`}>
      {image && !failed ? (
        <img
          src={image}
          alt={`Locandina di ${title.title}`}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <div
          className="poster-missing"
          role="img"
          aria-label={`Locandina non disponibile: ${title.title}`}
        >
          <ImageOff size={24} strokeWidth={1.3} />
        </div>
      )}
    </div>
  );
}

export function TitleCard({ title }: { title: Title }) {
  return (
    <article className="title-card">
      <a href={`#title/${title.id}`} aria-label={`Apri ${title.title}`}>
        <Poster title={title} />
        <h2>{title.title}</h2>
      </a>
      <div className="title-card-footer">
        <p>
          {title.year != null && <span>{title.year}</span>}
          <span>{categoryName(title.source_type)}</span>
        </p>
        <TitleActions title={title} variant="compact" />
      </div>
    </article>
  );
}
