// frontend/src/lib/api/streamBrief.ts
//
// SSE-via-fetch reader. EventSource is GET-only + no headers, so we POST
// + read the ReadableStream + parse 'data: ' lines manually. Returns an
// async generator yielding decoded events; caller `for await`s over it.
import type { LLMProvider } from "@/lib/byok";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app";

export type BriefEvent =
  | { type: "summary" | "bull" | "bear"; delta: string }
  | { type: "done" }
  | { type: "error"; message: string };

export interface StreamBriefBody {
  provider: LLMProvider;
  api_key: string;
  model?: string;
  base_url?: string;
}

export async function* streamBrief(
  ticker: string,
  body: StreamBriefBody,
  signal?: AbortSignal,
): AsyncGenerator<BriefEvent, void, void> {
  const r = await fetch(`${API_BASE}/api/brief/${ticker.toUpperCase()}/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!r.ok || !r.body) {
    let msg = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      msg = `${msg}: ${j.detail ?? JSON.stringify(j)}`;
    } catch {
      // body might not be JSON (e.g. 502 from edge)
    }
    yield { type: "error", message: msg };
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE events are separated by blank lines. A complete event ends
      // with "\n\n". Process all complete events in the buffer.
      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        for (const line of event.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice("data: ".length);
          try {
            yield JSON.parse(data) as BriefEvent;
          } catch {
            // Skip malformed event; continue with the next.
          }
        }
      }
    }
    // Flush any trailing event without separator (rare with FastAPI).
    if (buffer.trim().startsWith("data: ")) {
      try {
        yield JSON.parse(buffer.slice("data: ".length).trim()) as BriefEvent;
      } catch {
        /* ignore */
      }
    }
  } finally {
    reader.releaseLock();
  }
}
