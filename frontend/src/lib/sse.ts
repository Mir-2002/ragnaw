// Minimal Server-Sent Events reader for a fetch() body. EventSource can't POST, and /chat
// takes the question in a JSON body.

export type SseMessage = { event: string; data: string };

export async function* readSse(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  // stream: true keeps multi-byte characters (é, …) intact across chunk boundaries.
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Events end with a blank line; the spec allows \r\n and \r line endings too.
      let match: RegExpExecArray | null;
      while ((match = /\r\n\r\n|\n\n|\r\r/.exec(buffer))) {
        const message = parseBlock(buffer.slice(0, match.index));
        buffer = buffer.slice(match.index + match[0].length);
        if (message) yield message;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split(/\r\n|\n|\r/)) {
    // Lines starting with ":" are comments, e.g. the server's keep-alive pings.
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}
