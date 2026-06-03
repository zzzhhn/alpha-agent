// frontend/src/lib/api/streamNewsDaySummary.ts
//
// SSE-via-fetch reader for the per-day news summary + sentiment analysis.
// Mirrors streamPersona.ts: EventSource is GET-only + no headers, so we
// POST + read the ReadableStream + parse 'data: ' lines manually. Returns
// an async generator yielding typed events; the IntradayDrawer consumer
// `for await`s over it (AbortController ref = pause/Stop).
//
// The body carries the clicked candle's date + the page locale so the LLM
// output language follows the site language (no manual picker). The window
// (holiday backfill) is resolved server-side from the trading calendar.

// Browser: same-origin "" so /api/* goes through the Next.js middleware
// (which injects the auth Bearer header) and the next.config.mjs rewrite.
// Server (SSR): the absolute backend URL, since middleware does not run on
// server-component fetches. Auth-gated endpoints are only called client-side.
const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app"
    : "";

// Single-block prose, same event shape as persona commentary. `cache:
// "empty"` is the graceful "no news this day" done variant.
export type NewsDaySummaryEvent =
  | { type: "explanation"; delta: string }
  | { type: "done"; cache?: "hit" | "miss" | "empty" }
  | { type: "error"; message: string };

export async function* streamNewsDaySummary(
  ticker: string,
  date: string,
  lang: "zh" | "en",
  signal?: AbortSignal,
): AsyncGenerator<NewsDaySummaryEvent, void, void> {
  const r = await fetch(
    `${API_BASE}/api/stock/${ticker.toUpperCase()}/news-day-summary/stream`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include", // same-origin JWT cookie -> Bearer at the rewrite
      body: JSON.stringify({ date, language: lang }),
      signal,
    },
  );

  if (!r.ok || !r.body) {
    // Surface the HTTP status so the consumer can distinguish a 400 (no
    // BYOK key -> "configure key" CTA) from other failures.
    let detail = "";
    try {
      const j = await r.json();
      detail = j.detail ?? JSON.stringify(j);
    } catch {
      // body might not be JSON (e.g. 502 from edge)
    }
    yield {
      type: "error",
      message: `HTTP ${r.status}${detail ? `: ${detail}` : ""}`,
    };
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
            yield JSON.parse(data) as NewsDaySummaryEvent;
          } catch {
            // Skip malformed event; continue with the next.
          }
        }
      }
    }
    // Flush any trailing event without separator (rare with FastAPI).
    if (buffer.trim().startsWith("data: ")) {
      try {
        yield JSON.parse(buffer.slice("data: ".length).trim()) as NewsDaySummaryEvent;
      } catch {
        /* ignore */
      }
    }
  } finally {
    reader.releaseLock();
  }
}
