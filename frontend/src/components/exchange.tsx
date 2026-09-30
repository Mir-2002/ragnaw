"use client";

import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Frame, MoreArrow } from "@/components/retro";
import { charsPerSecond, type TextSpeed } from "@/hooks/use-text-speed";
import { useTypewriter } from "@/hooks/use-typewriter";
import type { Source } from "@/lib/api";
import { pixelSprite } from "@/lib/sprites";

export type Exchange = {
  id: string;
  question: string;
  steps: string[];
  answer: string;
  sources: Source[];
  phase: "working" | "done" | "error" | "stopped";
  error?: string;
  truncated?: boolean;
};

const KIND_LABELS: Record<Source["kind"], string> = {
  pokemon: "Pokémon",
  species: "Pokédex",
  move: "Move",
  ability: "Ability",
};

export function ExchangeView({
  exchange,
  speed,
  onRetry,
}: {
  exchange: Exchange;
  speed: TextSpeed;
  onRetry: (question: string) => void;
}) {
  const { question, steps, sources, phase } = exchange;
  const typed = useTypewriter(exchange.answer, charsPerSecond(speed));
  const working = phase === "working";
  const finished = !working && typed.done;

  return (
    <article className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Frame className="max-w-[85%]" fillClassName="px-text py-2 whitespace-pre-wrap">
          <span className="px-label mr-2 text-xs text-[var(--frame-band)]">You</span>
          {question}
        </Frame>
      </div>

      <Frame fillClassName="px-text relative flex flex-col gap-3 pb-6">
        {steps.length > 0 && <Steps steps={steps} active={working && !exchange.answer} />}

        {exchange.answer ? (
          <Markdown text={typed.text} />
        ) : working ? (
          <p className="text-[var(--ink-soft)]">
            Thinking<span className="px-blink">…</span>
          </p>
        ) : null}

        {exchange.truncated && finished && (
          <Notice message="The answer was cut off." action="Ask again" onAction={() => onRetry(question)} />
        )}
        {phase === "error" && (
          <Notice message={exchange.error ?? "Couldn’t answer that."} action="Retry" onAction={() => onRetry(question)} />
        )}
        {phase === "stopped" && <p className="text-[var(--ink-soft)]">You stopped this answer.</p>}

        {sources.length > 0 && finished && <Sources sources={sources} />}

        {finished && phase === "done" && <MoreArrow className="absolute right-4 bottom-2" />}
      </Frame>
    </article>
  );
}

function Steps({ steps, active }: { steps: string[]; active: boolean }) {
  return (
    <ul className="flex flex-col gap-0.5 text-[var(--ink-soft)]">
      {steps.map((step, i) => (
        <li key={i}>
          {step}
          {active && i === steps.length - 1 ? <span className="px-blink">…</span> : "."}
        </li>
      ))}
    </ul>
  );
}

function Notice({ message, action, onAction }: { message: string; action: string; onAction: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p>{message}</p>
      <button type="button" className="px-button px-label text-xs" onClick={onAction}>
        <span className="px-key">A</span> {action}
      </button>
    </div>
  );
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="px-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...withoutNode(props)} target="_blank" rel="noreferrer" />,
          table: (props) => (
            <div className="overflow-x-auto">
              <table {...withoutNode(props)} />
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

// react-markdown passes its AST node as a prop; keep it off the DOM element.
function withoutNode<T extends { node?: unknown }>(props: T): Omit<T, "node"> {
  const rest = { ...props };
  delete rest.node;
  return rest;
}

function Sources({ sources }: { sources: Source[] }) {
  return (
    <section className="flex flex-col gap-2 border-t-[length:var(--px)] border-dashed border-[var(--frame-light)] pt-3">
      <h3 className="px-label text-xs text-[var(--ink-soft)]">Sources</h3>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {sources.map((source) => {
          const sprite = source.image ? pixelSprite(source.image) : undefined;
          return (
            <li key={source.url}>
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-3 bg-[var(--stripe)] p-1.5 pr-3 hover:brightness-95"
              >
                {sprite ? (
                  // unoptimized: resizing would smooth the pixel art, and would spend Vercel's
                  // image optimization quota on 64px PNGs.
                  <Image
                    src={sprite}
                    alt=""
                    width={48}
                    height={48}
                    unoptimized
                    className="px-sprite size-12 shrink-0"
                  />
                ) : (
                  <span className="px-label grid size-12 shrink-0 place-items-center text-xs text-[var(--ink-soft)]">
                    {KIND_LABELS[source.kind]?.slice(0, 3)}
                  </span>
                )}
                <span className="px-label min-w-0 flex-1 truncate text-xs">{source.title}</span>
                <span className="px-label text-[10px] text-[var(--ink-soft)]">{KIND_LABELS[source.kind] ?? source.kind}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
