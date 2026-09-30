import type { BackendStatus } from "@/hooks/use-backend-status";
import type { Health } from "@/lib/api";
import { cn } from "@/lib/utils";

const LABELS: Record<BackendStatus, string> = {
  checking: "Connecting…",
  waking: "Waking up the backend…",
  online: "Online",
  offline: "Backend unreachable",
};

const DOT: Record<BackendStatus, string> = {
  checking: "bg-muted-foreground",
  waking: "bg-amber-400 animate-pulse",
  online: "bg-emerald-500",
  offline: "bg-destructive",
};

/** Why questions can't be asked yet, or null when they can. */
export function unavailableReason(status: BackendStatus, health: Health | null) {
  if (status === "waking") return "The backend is waking up. This can take up to a minute.";
  if (status === "offline") return "The backend isn't responding. Try reloading in a minute.";
  if (status === "checking" || !health) return "Connecting to the backend…";
  if (!health.data_ready) return "The Pokémon data hasn't been built on the backend.";
  if (!health.llm_providers.length) return "No LLM provider is configured on the backend.";
  return null;
}

export function BackendStatusPill({ status }: { status: BackendStatus }) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground"
      aria-live="polite"
    >
      <span className={cn("size-1.5 rounded-full", DOT[status])} />
      {LABELS[status]}
    </span>
  );
}
