"use client";

import { ArrowUpIcon, SquareIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { BackendStatusPill, unavailableReason } from "@/components/backend-status";
import { type Exchange, ExchangeView } from "@/components/exchange";
import { ThemeToggle } from "@/components/theme";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { ask, MAX_QUESTION_CHARS } from "@/lib/api";

const EXAMPLES = [
  "What type is Gengar and what is it weak to?",
  "What are the fastest Fire-type Pokémon?",
  "How does Eevee evolve into Umbreon?",
  "Is Mega Charizard X or Y better at physical attacking?",
  "Which Gen 4 Pokémon have Levitate?",
  "Which Pokémon has cheek sacs that store electricity?",
];

export function Chat() {
  const { status, health } = useBackendStatus();
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const unavailable = unavailableReason(status, health);
  const question = input.trim();
  const tooLong = question.length > MAX_QUESTION_CHARS;
  const canSend = !busy && !unavailable && question.length > 0 && !tooLong;

  // Keep the newest exchange in view as it streams.
  const last = exchanges.at(-1);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [last?.answer, last?.steps.length, last?.phase, exchanges.length]);

  function update(id: string, change: (e: Exchange) => Partial<Exchange>) {
    setExchanges((all) => all.map((e) => (e.id === id ? { ...e, ...change(e) } : e)));
  }

  async function send(text: string) {
    const id = crypto.randomUUID();
    setExchanges((all) => [
      ...all,
      { id, question: text, steps: [], answer: "", sources: [], phase: "working" },
    ]);
    setInput("");
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of ask(text, controller.signal)) {
        switch (event.type) {
          case "status":
            update(id, (e) => ({ steps: [...e.steps, event.text] }));
            break;
          case "token":
            update(id, (e) => ({ answer: e.answer + event.text }));
            break;
          case "sources":
            update(id, () => ({ sources: event.sources }));
            break;
          case "done":
            update(id, () => ({ phase: "done", truncated: event.truncated }));
            break;
          case "error":
            update(id, () => ({ phase: "error", error: event.message }));
            break;
        }
      }
      // A stream that closes without done/error (e.g. the connection dropped).
      update(id, (e) =>
        e.phase === "working" ? { phase: e.answer ? "done" : "error", truncated: !!e.answer,
          error: e.answer ? undefined : "The connection closed before an answer arrived." } : {},
      );
    } catch (error) {
      if (controller.signal.aborted) {
        update(id, () => ({ phase: "stopped" }));
      } else {
        const message = error instanceof Error ? error.message : "Something went wrong.";
        update(id, () => ({
          phase: "error",
          error: error instanceof TypeError ? "Couldn't reach the backend." : message,
        }));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-3xl flex-col">
      <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-baseline gap-2">
          <h1 className="text-lg font-semibold tracking-tight">RAGNaw</h1>
          <span className="hidden text-sm text-muted-foreground sm:inline">
            Pokémon answers from PokeAPI data
          </span>
        </div>
        <div className="flex items-center gap-1">
          <BackendStatusPill status={status} />
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-6">
        {exchanges.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <div className="flex flex-col gap-2">
              <h2 className="text-2xl font-semibold tracking-tight">Ask anything about Pokémon</h2>
              <p className="text-sm text-muted-foreground">
                Stats, types, matchups, evolutions, moves, abilities and Pokédex lore, as of the
                latest games.
              </p>
            </div>
            <div className="flex max-w-xl flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <Button
                  key={example}
                  variant="outline"
                  size="sm"
                  disabled={!!unavailable}
                  onClick={() => send(example)}
                >
                  {example}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            {exchanges.map((exchange) => (
              <ExchangeView
                key={exchange.id}
                exchange={exchange}
                onRetry={(q) => !busy && send(q)}
              />
            ))}
            <div ref={endRef} />
          </div>
        )}
      </main>

      <footer className="border-t px-4 pt-3 pb-4">
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSend) send(question);
          }}
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter adds a line. Skip while an IME is composing.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (canSend) send(question);
              }
            }}
            placeholder={unavailable ?? "Ask about a Pokémon, move, ability or type…"}
            aria-label="Your question"
            aria-invalid={tooLong || undefined}
            rows={1}
            className="max-h-40 min-h-10 resize-none"
          />
          {busy ? (
            <Button
              type="button"
              size="icon-lg"
              variant="outline"
              aria-label="Stop"
              onClick={() => abortRef.current?.abort()}
            >
              <SquareIcon />
            </Button>
          ) : (
            <Button type="submit" size="icon-lg" aria-label="Send" disabled={!canSend}>
              <ArrowUpIcon />
            </Button>
          )}
        </form>
        <div className="mt-2 flex justify-between gap-4 text-xs text-muted-foreground">
          <span>
            Unofficial fan project. Pokémon © Nintendo, Game Freak, Creatures. Data from{" "}
            <a href="https://pokeapi.co" target="_blank" rel="noreferrer" className="underline underline-offset-2">
              PokeAPI
            </a>
            .
          </span>
          {question.length > MAX_QUESTION_CHARS * 0.8 && (
            <span className={tooLong ? "text-destructive" : undefined}>
              {question.length}/{MAX_QUESTION_CHARS}
            </span>
          )}
        </div>
      </footer>
    </div>
  );
}
