import { ArrowUpRight, ImageOff, Star } from "lucide-react";
import { useState } from "react";
import { categoryName, type Title } from "@/lib/api";

export function Poster({
  title,
  className = "",
}: {
  title: Title;
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
        <div className="poster-missing">
          <ImageOff size={24} strokeWidth={1.3} />
          <span>{title.title}</span>
        </div>
      )}
    </div>
  );
}

export function TitleCard({ title }: { title: Title }) {
  const rating = title.metadata.ratings[0];
  return (
    <a
      className="title-card"
      href={`#title/${title.id}`}
      aria-label={`Apri ${title.title}`}
    >
      <div className="poster-wrap">
        <Poster title={title} />
        <span className="open-card">
          <ArrowUpRight size={18} />
        </span>
      </div>
      <div className="card-meta">
        <span>
          {categoryName(title.source_type)} · {title.year ?? "Anno n.d."}
        </span>
        {rating && (
          <span className="rating" title={`Voto ${rating.source}`}>
            <Star size={12} />
            {rating.value.toFixed(1)}
          </span>
        )}
      </div>
      <h2>{title.title}</h2>
      <p>
        {(title.genres ?? []).slice(0, 2).join(" · ") ||
          "Genere non disponibile"}
      </p>
    </a>
  );
}
