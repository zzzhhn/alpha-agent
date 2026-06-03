// frontend/src/lib/api/streamNewsEnrich.ts
//
// SSE-via-fetch reader for progressive news enrichment. Mirrors
// streamBrief.ts: POST + read the ReadableStream + parse 'data: ' lines.
// Returns an async generator yielding typed progress events so NewsBlock
// can fill the list in place (no full-page reload).
//
// Granularity: news enrichment is structurally a *batch* LLM call (15
// headlines -> one JSON array), so the honest streaming unit is per-batch.
// Each "items" event carries every row that batch enriched; the consumer
// splices them into the list by id.

// Browser: same-origin "" so /api/* goes through the Next.js middleware
// (which injects the auth Bearer header) and the next.config.mjs rewrite.
const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app"
    : "";

export interface EnrichedNewsItem {
  id: number;
  sentiment_score: number | null;
  sentiment_label: "pos" | "neg" | "neu" | null;
  reasoning_text: string | null;
  reasoning_lang: string | null;
}

export type NewsEnrichEvent =
  | { type: "start"; pending: number }
  | { type: "items"; items: EnrichedNewsItem[] }
  | { type: "batch_failed" }
  | { type: "done"; enriched: number; failed_batches: number }
  | { type: "error"; message: string };

export async function* streamNewsEnrich(
  ticker: string,
  lang: "zh" | "en",
  signal?: AbortSignal,
): AsyncGenerator<NewsEnrichEvent, void, void> {
  const r = await fetch(
    `${API_BASE}/api/news/enrich/${ticker.toUpperCase()}/stream?lang=${lang}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include", // same-origin JWT cookie -> Bearer at the rewrite
      body: "{}",
      signal,
    },
  );

  if (!r.ok || !r.body) {
    // Surface the HTTP status so the consumer can distinguish a 400
    // (no BYOK key -> "configure key" CTA) from other failures.
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
      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        for (const line of event.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice("data: ".length);
          try {
            yield JSON.parse(data) as NewsEnrichEvent;
          } catch {
            // Skip malformed event; continue with the next.
          }
        }
      }
    }
    if (buffer.trim().startsWith("data: ")) {
      try {
        yield JSON.parse(buffer.slice("data: ".length).trim()) as NewsEnrichEvent;
      } catch {
        /* ignore */
      }
    }
  } finally {
    reader.releaseLock();
  }
}
