import type { BackendStatus } from "@/hooks/use-backend-status";
import type { Health } from "@/lib/api";
import { cn } from "@/lib/utils";

const LABELS: Record<BackendStatus, string> = {
  checking: "Connecting",
  waking: "Waking up",
  online: "Online",
  offline: "Offline",
};

const DOT: Record<BackendStatus, string> = {
  checking: "bg-[var(--ink-soft)]",
  waking: "bg-amber-400 px-blink",
  online: "bg-emerald-500",
  offline: "bg-[var(--accent)]",
};

/** Why questions can't be asked yet, or null when they can. */
export function unavailableReason(status: BackendStatus, health: Health | null) {
  if (status === "waking") return "The server is waking up. On the free tier this can take a minute.";
  if (status === "offline") return "The server isn’t responding. Reload the page in a minute.";
  if (status === "checking" || !health) return "Connecting to the server…";
  if (!health.data_ready) return "The server doesn’t have its Pokémon data yet.";
  if (!health.llm_providers.length) return "The server has no language model configured.";
  return null;
}

export function BackendStatusPill({ status }: { status: BackendStatus }) {
  return (
    <span className="px-label inline-flex items-center gap-2 text-xs" aria-live="polite">
      <span className={cn("size-2", DOT[status])} />
      {LABELS[status]}
    </span>
  );
}
