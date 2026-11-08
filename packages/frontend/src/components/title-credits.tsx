import { ScrollArea } from "@/components/ui/scroll-area";
import type { Credit } from "@/lib/api";

export function TitleCredits({
  heading,
  people,
}: {
  heading: string;
  people: Credit[];
}) {
  if (!people.length) return null;
  return (
    <section className="detail-section min-w-0">
      <h3>{heading}</h3>
      <ScrollArea
        className="credits"
        viewportProps={{ "aria-label": heading, role: "region", tabIndex: 0 }}
      >
        <ul className="pr-4">
          {people.map((person, index) => (
            <li key={`${person.source_id}-${person.role}-${index}`}>
              <span>{person.name}</span>
              <small>
                {[person.character, person.role, person.language]
                  .filter(Boolean)
                  .join(" · ")}
              </small>
            </li>
          ))}
        </ul>
      </ScrollArea>
    </section>
  );
}
