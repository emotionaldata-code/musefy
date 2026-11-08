import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Exchange = { id: string; text: string };

export function Chat({ active }: { active: boolean }) {
  const [draft, setDraft] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const conversation = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (active && conversation.current) {
      conversation.current.scrollTop = conversation.current.scrollHeight;
    }
  }, [active, exchanges]);

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim()) return;
    setExchanges((current) => [
      ...current,
      { id: crypto.randomUUID(), text: draft },
    ]);
    setDraft("");
    composer.current?.focus();
  }

  return (
    <section className="chat" aria-label="Chat Musefy" hidden={!active}>
      <div
        className="chat-conversation"
        role="log"
        aria-label="Conversazione"
        aria-live="polite"
        tabIndex={0}
        ref={conversation}
      >
        {exchanges.length === 0 ? (
          <div className="chat-empty">
            <h2>Scrivi a Musefy</h2>
            <p>Per ora ripeto i tuoi messaggi.</p>
          </div>
        ) : (
          <div className="chat-messages">
            {exchanges.map((exchange) => (
              <div className="chat-exchange" key={exchange.id}>
                <div className="chat-message chat-message-user">
                  <span className="sr-only">Tu: </span>
                  <p>{exchange.text}</p>
                </div>
                <div className="chat-message chat-message-assistant">
                  <span className="chat-speaker">Musefy</span>
                  <p>{exchange.text}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <form
        className="chat-composer"
        aria-label="Invia un messaggio"
        onSubmit={send}
      >
        <Textarea
          ref={composer}
          aria-label="Messaggio"
          placeholder="Scrivi un messaggio…"
          value={draft}
          rows={1}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <Button
          type="submit"
          size="icon"
          className="icon-button"
          aria-label="Invia messaggio"
          disabled={!draft.trim()}
        >
          <ArrowUp aria-hidden="true" />
        </Button>
      </form>
    </section>
  );
}
