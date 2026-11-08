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

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!active || !viewport) return;
    const root = document.documentElement;
    function resize() {
      if (!viewport || viewport.scale !== 1) return;
      root.style.setProperty("--chat-viewport-height", `${viewport.height}px`);
      root.style.setProperty("--chat-viewport-top", `${viewport.offsetTop}px`);
    }
    resize();
    viewport.addEventListener("resize", resize);
    viewport.addEventListener("scroll", resize);
    return () => {
      viewport.removeEventListener("resize", resize);
      viewport.removeEventListener("scroll", resize);
      root.style.removeProperty("--chat-viewport-height");
      root.style.removeProperty("--chat-viewport-top");
    };
  }, [active]);

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
    <section
      className="chat flex min-h-0 flex-1 flex-col"
      aria-label="Chat Musefy"
      hidden={!active}
    >
      <div
        className="chat-conversation relative min-h-0 flex-1 overflow-y-auto overscroll-contain"
        role="log"
        aria-label="Conversazione"
        aria-live="polite"
        tabIndex={0}
        ref={conversation}
      >
        {exchanges.length === 0 ? (
          <div className="chat-empty flex min-h-full flex-col items-center justify-center gap-2 px-4 pb-10 text-center">
            <h2 className="text-2xl font-medium tracking-tight sm:text-[1.75rem]">
              Scrivi a Musefy
            </h2>
            <p className="text-sm text-muted-foreground">
              Per ora ripeto i tuoi messaggi.
            </p>
          </div>
        ) : (
          <div className="chat-messages mx-auto w-full max-w-180 space-y-7 px-1 py-5 sm:space-y-8 sm:pb-8">
            {exchanges.map((exchange) => (
              <div className="chat-exchange" key={exchange.id}>
                <div className="chat-message chat-message-user ml-auto w-fit max-w-[88%] rounded-3xl bg-card px-4 py-3 whitespace-pre-wrap [overflow-wrap:anywhere] sm:max-w-[85%] sm:px-5">
                  <span className="sr-only">Tu: </span>
                  <p className="leading-relaxed">{exchange.text}</p>
                </div>
                <div className="chat-message chat-message-assistant mt-5 whitespace-pre-wrap [overflow-wrap:anywhere] sm:mt-6">
                  <span className="chat-speaker mb-2 block text-sm font-semibold">
                    Musefy
                  </span>
                  <p className="leading-relaxed">{exchange.text}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <form
        className="chat-composer mx-auto mt-3 flex w-full max-w-180 shrink-0 items-end gap-2 rounded-[1.75rem] bg-card p-2 sm:mt-4 sm:gap-3 sm:p-2.5"
        aria-label="Invia un messaggio"
        onSubmit={send}
      >
        <Textarea
          ref={composer}
          className="min-w-0 flex-1 resize-none"
          enterKeyHint="send"
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
