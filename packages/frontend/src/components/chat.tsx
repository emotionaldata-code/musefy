import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { ChatReply } from "@/components/chat-reply";
import { ChatActions } from "@/components/chat-actions";
import { categoryName, type Kind } from "@/lib/api";
import { useRecommendations } from "@/lib/use-recommendations";

const formats: Kind[] = ["movie", "tv", "anime", "manga"];

export function Chat({ active }: { active: boolean }) {
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<Kind | null>(null);
  const [editing, setEditing] = useState(true);
  const { exchanges, pending, hasMore, send, more, reset, retry } =
    useRecommendations();
  const conversation = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const firstFormat = useRef<HTMLButtonElement>(null);
  const loadingMore = pending && (exchanges.at(-1)?.offset ?? 0) > 0;

  useEffect(() => {
    if (!active || !editing) return;
    if (kind) composer.current?.focus();
    else firstFormat.current?.focus();
  }, [active, editing, kind]);

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

  function choose(format: Kind): void {
    setKind(format);
  }

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (kind && send(draft, kind)) {
      setDraft("");
      setEditing(false);
    }
  }

  function edit(): void {
    setDraft(exchanges.at(-1)?.text ?? "");
    setEditing(true);
  }

  function restart(): void {
    reset();
    setDraft("");
    setKind(null);
    setEditing(true);
  }

  return (
    <section
      className="chat flex min-h-0 flex-1 flex-col"
      aria-label="Chat Musefy"
      hidden={!active}
    >
      <ScrollArea
        className="chat-conversation min-h-0 flex-1"
        viewportProps={{
          ref: conversation,
          role: "log",
          "aria-label": "Conversazione",
          "aria-live": "polite",
          tabIndex: 0,
          className: "overscroll-contain",
        }}
      >
        {exchanges.length === 0 ? (
          <div className="chat-empty flex min-h-full flex-col items-center justify-center gap-3 px-3 py-8 text-center sm:py-16">
            <h2 className="text-2xl font-medium tracking-tight sm:text-[1.75rem]">
              Cosa vuoi farti consigliare?
            </h2>
            <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
              {kind
                ? "Descrivi un tema, una trama o un’atmosfera."
                : "Scegli un formato per iniziare."}
            </p>
            <div
              role="group"
              aria-label="Formato da consigliare"
              className="mt-2 flex flex-wrap justify-center gap-2"
            >
              {formats.map((format) => (
                <Button
                  key={format}
                  ref={format === formats[0] ? firstFormat : undefined}
                  variant={kind === format ? "default" : "secondary"}
                  aria-pressed={kind === format}
                  className="min-h-11 px-5"
                  onClick={() => choose(format)}
                >
                  {categoryName(format)}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-messages mx-auto w-full max-w-180 space-y-7 px-1 py-5 pr-3 sm:space-y-8 sm:pb-8">
            {exchanges.map((exchange) => (
              <div className="chat-exchange" key={exchange.id}>
                <div className="chat-message chat-message-user ml-auto w-fit max-w-[88%] rounded-3xl bg-card px-4 py-3 whitespace-pre-wrap [overflow-wrap:anywhere] sm:max-w-[85%] sm:px-5">
                  <span className="sr-only">
                    Tu, {categoryName(exchange.kind)}:{" "}
                  </span>
                  <p className="leading-relaxed">
                    {exchange.offset ? "Altri consigli" : exchange.text}
                  </p>
                </div>
                <div className="chat-message chat-message-assistant mt-5 [overflow-wrap:anywhere] sm:mt-6">
                  <span className="chat-speaker mb-3 block text-sm font-semibold">
                    Musefy
                  </span>
                  <ChatReply
                    exchange={exchange}
                    pending={pending}
                    retry={retry}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
      {!editing && (
        <ChatActions
          pending={pending}
          hasMore={hasMore || loadingMore}
          more={more}
          edit={edit}
          reset={restart}
        />
      )}
      {editing && (
        <>
          {exchanges.length > 0 && (
            <div className="mx-auto w-full max-w-180 shrink-0 pt-2">
              <Button
                variant="ghost"
                className="min-h-11"
                onClick={() => setEditing(false)}
              >
                Annulla modifica
              </Button>
            </div>
          )}
          <form
            className="chat-composer mx-auto mt-3 flex w-full max-w-180 shrink-0 items-end gap-2 rounded-[1.75rem] bg-card p-2 sm:mt-4 sm:gap-3 sm:p-2.5"
            aria-label="Invia un messaggio"
            onSubmit={submit}
          >
            <Textarea
              ref={composer}
              className="min-w-0 flex-1 resize-none"
              enterKeyHint="send"
              aria-label="Messaggio"
              aria-describedby="chat-hint"
              placeholder={
                kind
                  ? "Che storia hai in mente?"
                  : "Scegli un formato per iniziare…"
              }
              value={draft}
              disabled={!kind}
              rows={1}
              maxLength={200}
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
              disabled={!kind || !draft.trim() || pending}
            >
              <ArrowUp aria-hidden="true" />
            </Button>
          </form>
          <p
            id="chat-hint"
            className="mx-auto mt-2 w-full max-w-180 shrink-0 px-3 text-xs leading-relaxed text-muted-foreground"
          >
            {draft.length === 200
              ? "Limite di 200 caratteri raggiunto."
              : kind
                ? "Fino a 200 caratteri."
                : "Scegli un formato per scrivere."}
          </p>
        </>
      )}
    </section>
  );
}
