"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { BackendStatusPill, unavailableReason } from "@/components/backend-status";
import { AboutDialog, OptionDialog } from "@/components/dialogs";
import { type Exchange, ExchangeView } from "@/components/exchange";
import { Frame } from "@/components/retro";
import { StartMenu } from "@/components/start-menu";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { useTextSpeed } from "@/hooks/use-text-speed";
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
  const [speed] = useTextSpeed();
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<"option" | "about" | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Follow the conversation while the reader is at the bottom; stop if they scroll up.
  const stickToBottom = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const unavailable = unavailableReason(status, health);
  const question = input.trim();
  const tooLong = question.length > MAX_QUESTION_CHARS;
  const canAsk = !busy && !unavailable;
  const canSend = canAsk && question.length > 0 && !tooLong;

  // The typewriter keeps growing the answer after the stream ends, so follow the list's
  // size rather than its data.
  const hasExchanges = exchanges.length > 0;
  useEffect(() => {
    const main = mainRef.current;
    const list = listRef.current;
    if (!main || !list) return;
    const observer = new ResizeObserver(() => {
      if (stickToBottom.current) main.scrollTop = main.scrollHeight;
    });
    observer.observe(list);
    return () => observer.disconnect();
  }, [hasExchanges]);

  // B button: Escape stops an answer in progress (menus and dialogs handle their own).
  useEffect(() => {
    if (!busy) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !dialog) abortRef.current?.abort();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, dialog]);

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
    stickToBottom.current = true;
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
        e.phase !== "working"
          ? {}
          : e.answer
            ? { phase: "done", truncated: true }
            : { phase: "error", error: "The connection closed before an answer arrived." },
      );
    } catch (error) {
      if (controller.signal.aborted) {
        update(id, () => ({ phase: "stopped" }));
      } else {
        const message = error instanceof Error ? error.message : "Something went wrong.";
        update(id, () => ({
          phase: "error",
          error: error instanceof TypeError ? "Couldn’t reach the server." : message,
        }));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-3xl flex-col gap-3 p-3 sm:p-4">
      {/* One sign across the top, like the location popup on entering a new area. */}
      <header>
        <Frame fillClassName="px-text flex items-center justify-between gap-3 py-2">
          <div className="min-w-0">
            <h1 className="leading-none">
              {/* The letters sit on a 28-unit pixel grid: 21px and 28px tall keep every
                  edge on a whole screen pixel. */}
              <Image
                src="/ragnaw-wordmark.svg"
                alt="RAGNaw"
                width={1316}
                height={196}
                priority
                unoptimized
                className="px-logo h-[21px] w-auto sm:h-7"
              />
            </h1>
            <p className="px-label mt-1.5 truncate text-[10px] text-[var(--ink-soft)]">
              Pokémon answers from PokeAPI data
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <BackendStatusPill status={status} />
            <StartMenu
              examples={EXAMPLES}
              canAsk={canAsk}
              canClear={!busy && exchanges.length > 0}
              onAsk={send}
              onNewChat={() => setExchanges([])}
              onOption={() => setDialog("option")}
              onAbout={() => setDialog("about")}
            />
          </div>
        </Frame>
      </header>

      <main
        ref={mainRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="-mx-1 flex-1 overflow-y-auto px-1 py-2"
      >
        {exchanges.length === 0 ? (
          <div className="flex h-full flex-col justify-end">
            <Frame fillClassName="px-text flex flex-col gap-3">
              <p className="leading-snug">
                {unavailable ??
                  "Hi! Ask me about any Pokémon, move, ability or type, and I’ll look it up in PokeAPI’s data."}
              </p>
              {!unavailable && (
                <>
                  <p className="text-[var(--ink-soft)]">Try one:</p>
                  <ExampleList examples={EXAMPLES} onPick={send} />
                </>
              )}
            </Frame>
          </div>
        ) : (
          <div ref={listRef} className="flex flex-col gap-6">
            {exchanges.map((exchange) => (
              <ExchangeView
                key={exchange.id}
                exchange={exchange}
                speed={speed}
                onRetry={(q) => !busy && send(q)}
              />
            ))}
          </div>
        )}
      </main>

      <footer className="flex flex-col gap-2">
        <Frame fillClassName="px-text py-3">
          <form
            className="flex items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (canSend) send(question);
            }}
          >
            <label className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="px-label text-xs text-[var(--frame-band)]">Your question</span>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  // Enter asks; Shift+Enter adds a line. Skip while an IME is composing.
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (canSend) send(question);
                  }
                }}
                placeholder="e.g. What is Gengar weak to?"
                aria-invalid={tooLong || undefined}
                rows={1}
                className="field-sizing-content max-h-32 min-h-8 resize-none bg-transparent leading-snug outline-none placeholder:text-[var(--ink-soft)] placeholder:opacity-70"
              />
            </label>
            {busy ? (
              <button type="button" className="px-button px-label text-xs" onClick={() => abortRef.current?.abort()}>
                <span className="px-key">B</span> Stop
              </button>
            ) : (
              <button type="submit" className="px-button px-label text-xs" disabled={!canSend}>
                <span className="px-key">A</span> Ask
              </button>
            )}
          </form>
          <p className="px-label mt-2 flex justify-between gap-3 text-[10px] text-[var(--ink-soft)]">
            {/* Keyboard hints; touch screens have no Enter/Shift to speak of. */}
            <span className="hidden sm:inline">Enter to ask · Shift+Enter for a new line · Start for the menu</span>
            {question.length > MAX_QUESTION_CHARS * 0.8 && (
              <span className={tooLong ? "text-[var(--accent)]" : undefined}>
                {question.length}/{MAX_QUESTION_CHARS}
              </span>
            )}
          </p>
        </Frame>
        <p className="px-text px-label text-center text-[10px] [--ink:#f8f8f8] [--ink-shadow:#283878]">
          Unofficial fan project. Pokémon © Nintendo, Game Freak, Creatures. Data from PokeAPI.
        </p>
      </footer>

      <OptionDialog open={dialog === "option"} onOpenChange={(open) => setDialog(open ? "option" : null)} />
      <AboutDialog open={dialog === "about"} onOpenChange={(open) => setDialog(open ? "about" : null)} />
    </div>
  );
}

/** Sample questions as a menu list: ↑/↓ move the ▶ cursor, Enter asks. */
function ExampleList({ examples, onPick }: { examples: string[]; onPick: (q: string) => void }) {
  function onKeyDown(e: React.KeyboardEvent<HTMLUListElement>) {
    const step = { ArrowUp: -1, ArrowDown: 1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const buttons = [...e.currentTarget.querySelectorAll("button")];
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    buttons[(at + step + buttons.length) % buttons.length]?.focus();
  }

  return (
    <ul className="flex flex-col gap-1" onKeyDown={onKeyDown}>
      {examples.map((example) => (
        <li key={example}>
          <button
            type="button"
            className="px-cursor w-full cursor-pointer py-0.5 text-left outline-none focus-visible:outline-none"
            onClick={() => onPick(example)}
          >
            {example}
          </button>
        </li>
      ))}
    </ul>
  );
}
