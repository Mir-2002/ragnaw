import { AlertCircleIcon, CheckIcon, Loader2Icon, RotateCcwIcon, ScissorsIcon } from "lucide-react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Source } from "@/lib/api";

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
  onRetry,
}: {
  exchange: Exchange;
  onRetry: (question: string) => void;
}) {
  const { question, steps, answer, sources, phase } = exchange;
  const working = phase === "working";

  return (
    <article className="flex flex-col gap-3">
      <p className="self-end rounded-2xl rounded-br-sm bg-muted px-4 py-2 text-sm whitespace-pre-wrap">
        {question}
      </p>

      <Card size="sm" className="gap-3">
        <CardContent className="flex flex-col gap-3">
          {steps.length > 0 && <Steps steps={steps} active={working && !answer} />}

          {answer ? (
            <Markdown text={answer} streaming={working} />
          ) : working ? (
            <div className="flex flex-col gap-2" aria-label="Waiting for the answer">
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="h-4 w-3/5" />
            </div>
          ) : null}

          {exchange.truncated && (
            <Alert>
              <ScissorsIcon />
              <AlertTitle>The answer was cut off</AlertTitle>
              <AlertDescription>The model’s response ended early.</AlertDescription>
              <AlertAction>
                <Button size="sm" variant="outline" onClick={() => onRetry(question)}>
                  <RotateCcwIcon data-icon="inline-start" /> Ask again
                </Button>
              </AlertAction>
            </Alert>
          )}

          {phase === "error" && (
            <Alert variant="destructive">
              <AlertCircleIcon />
              <AlertTitle>Couldn’t answer that</AlertTitle>
              <AlertDescription>{exchange.error}</AlertDescription>
              <AlertAction>
                <Button size="sm" variant="outline" onClick={() => onRetry(question)}>
                  <RotateCcwIcon data-icon="inline-start" /> Retry
                </Button>
              </AlertAction>
            </Alert>
          )}

          {phase === "stopped" && <p className="text-xs text-muted-foreground">Stopped.</p>}

          {sources.length > 0 && <Sources sources={sources} />}
        </CardContent>
      </Card>
    </article>
  );
}

function Steps({ steps, active }: { steps: string[]; active: boolean }) {
  return (
    <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
      {steps.map((step, i) => {
        const current = active && i === steps.length - 1;
        return (
          <li key={i} className="flex items-center gap-1.5">
            {current ? (
              <Loader2Icon className="size-3.5 animate-spin" />
            ) : (
              <CheckIcon className="size-3.5" />
            )}
            {step}
          </li>
        );
      })}
    </ul>
  );
}

function Markdown({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert prose-table:my-2 prose-th:py-1 prose-td:py-1">
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
      {streaming && (
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-foreground align-middle" />
      )}
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
    <section className="flex flex-col gap-2 border-t pt-3">
      <h3 className="text-xs font-medium text-muted-foreground">Sources</h3>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {sources.map((source) => (
          <li key={source.url}>
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-3 rounded-lg border p-2 text-sm transition-colors hover:bg-muted"
            >
              {source.image ? (
                // unoptimized: sprites are already small PNGs, and resizing them would
                // spend Vercel's image optimization quota for nothing.
                <Image
                  src={source.image}
                  alt=""
                  width={40}
                  height={40}
                  unoptimized
                  className="size-10 shrink-0 object-contain"
                />
              ) : (
                <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-xs text-muted-foreground">
                  {source.title.slice(0, 2)}
                </span>
              )}
              <span className="min-w-0 flex-1 truncate font-medium">{source.title}</span>
              <Badge variant="secondary">{KIND_LABELS[source.kind] ?? source.kind}</Badge>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
