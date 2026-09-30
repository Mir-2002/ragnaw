"use client";

import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";

export type BackendStatus = "checking" | "waking" | "online" | "offline";

// Free HF Spaces sleep when idle; a cold start can take a minute or more.
const WAKE_TIMEOUT_MS = 120_000;
const RETRY_MS = 3_000;

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>("checking");
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

  return { status, health };
}
