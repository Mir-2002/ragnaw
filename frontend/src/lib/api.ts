import { readSse } from "@/lib/sse";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

// Mirrors the backend's max_question_chars.
export const MAX_QUESTION_CHARS = 500;

export type Health = {
  status: "ok";
  data_ready: boolean;
  llm_providers: string[];
};

export type Source = {
  title: string;
  kind: "pokemon" | "species" | "move" | "ability";
  url: string;
  image?: string;
};

export type ChatEvent =
  | { type: "status"; text: string }
  | { type: "token"; text: string }
  | { type: "sources"; sources: Source[] }
  | { type: "done"; provider: string; rounds: number; truncated: boolean }
  | { type: "error"; message: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

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

/** Ask a question and yield the answer's events as they stream in. */
export async function* ask(question: string, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    signal,
  });

  if (!res.ok || !res.body) {
    // Rejections (422, 429, 503) come back as JSON before any streaming starts.
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Not JSON, e.g. an HF proxy page while the Space restarts.
    }
    throw new ApiError(message, res.status);
  }

  for await (const { event, data } of readSse(res.body)) {
    const payload = JSON.parse(data);
    switch (event) {
      case "status":
      case "token":
        yield { type: event, text: payload.text };
        break;
      case "sources":
        yield { type: "sources", sources: payload };
        break;
      case "done":
        yield { type: "done", ...payload };
        break;
      case "error":
        yield { type: "error", message: payload.message };
        break;
    }
  }
}
