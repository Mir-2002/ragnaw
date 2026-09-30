"use client";

import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";

type Status = "checking" | "waking" | "online" | "offline";

// Free HF Spaces sleep when idle; a cold start can take a minute or more.
const WAKE_TIMEOUT_MS = 120_000;
const RETRY_MS = 3_000;

const LABELS: Record<Status, string> = {
  checking: "Connecting…",
  waking: "Waking up the backend…",
  online: "Backend online",
  offline: "Backend unreachable",
};

const DOT: Record<Status, string> = {
  checking: "bg-zinc-400",
  waking: "bg-amber-400 animate-pulse",
  online: "bg-emerald-500",
  offline: "bg-red-500",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let cancelled = false;
    const started = Date.now();

    async function poll() {
      while (!cancelled && Date.now() - started < WAKE_TIMEOUT_MS) {
        const result = await getHealth();
        if (cancelled) return;
        if (result) {
          setHealth(result);
          setStatus("online");
          return;
        }
        setStatus("waking");
        await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
      }
      if (!cancelled) setStatus("offline");
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  const note =
    status === "online" && health && !health.data_ready
      ? "Index not built yet"
      : status === "waking"
        ? "This can take up to a minute on the free tier."
        : null;

  return (
    <div className="flex flex-col items-center gap-1 text-sm" aria-live="polite">
      <span className="inline-flex items-center gap-2 rounded-full border border-zinc-200 px-3 py-1 dark:border-zinc-800">
        <span className={`size-2 rounded-full ${DOT[status]}`} />
        {LABELS[status]}
      </span>
      {note && <span className="text-zinc-500">{note}</span>}
    </div>
  );
}
