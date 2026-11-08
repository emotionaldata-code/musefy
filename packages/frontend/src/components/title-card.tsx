import { ImageOff } from "lucide-react";
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
  return (
    <a
      className="title-card"
      href={`#title/${title.id}`}
      aria-label={`Apri ${title.title}`}
    >
      <Poster title={title} />
      <h2>{title.title}</h2>
      <p>
        {[title.year, categoryName(title.source_type)]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </a>
  );
}
