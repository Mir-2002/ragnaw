export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

export type Health = {
  status: "ok";
  data_ready: boolean;
  llm_providers: string[];
};

export async function getHealth(timeoutMs = 10_000): Promise<Health | null> {
  try {
    const res = await fetch(`${API_URL}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    // A waking HF Space answers with a non-2xx placeholder until the container is up.
    return res.ok ? ((await res.json()) as Health) : null;
  } catch {
    return null;
  }
}
