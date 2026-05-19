// frontend/src/lib/api/client.ts
import type { paths } from "../../../api-types.gen";

// Browser: same-origin "" so /api/* goes through the Next.js middleware
// (which injects the auth Bearer header) and the next.config.mjs rewrite.
// Server (SSR): the absolute backend URL, since middleware does not run on
// server-component fetches. Auth-gated endpoints are only called client-side.
const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app"
    : "";

type ApiError = { code: string; message: string; retry_after_sec?: number };

export class ApiException extends Error {
  constructor(public status: number, public body: ApiError) {
    super(body.message);
  }
}

/**
 * Optional caching directives for apiGet. Only honoured by Next.js when the
 * fetch runs server-side (Server Components, Route Handlers). The browser
 * ignores `next`, so client-side callers should leave this undefined to keep
 * the historical `cache: "no-store"` behaviour for live data.
 *
 * Server-side examples:
 *   fetchStock(ticker, { revalidate: 60, tags: [`stock-${ticker}`] })
 *   fetchPicks(50, undefined, undefined, { revalidate: 60, tags: ["picks-lean"] })
 */
export interface ApiGetOptions {
  // Seconds before the cached entry is considered stale. `false` = cache
  // forever (until tag-based revalidation). Omit to opt out of caching.
  revalidate?: number | false;
  // Cache tags for revalidateTag() invalidation from server actions.
  tags?: string[];
}

export async function apiGet<T>(path: string, opts?: ApiGetOptions): Promise<T> {
  type NextFetchInit = RequestInit & {
    next?: { revalidate?: number | false; tags?: string[] };
  };
  const init: NextFetchInit = {
    headers: { "content-type": "application/json" },
  };
  if (opts?.revalidate !== undefined || opts?.tags) {
    // Server-side cache opt-in. `cache` field omitted because it is
    // mutually exclusive with `next` on Next.js's fetch.
    init.next = {
      ...(opts.revalidate !== undefined ? { revalidate: opts.revalidate } : {}),
      ...(opts.tags ? { tags: opts.tags } : {}),
    };
  } else {
    // Historical default: opt-out of both Next Data Cache and HTTP cache.
    // Client-side callers (most components in /stock and /picks) want
    // fresh data on every navigation.
    init.cache = "no-store";
  }
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as ApiError;
    throw new ApiException(r.status, body);
  }
  return (await r.json()) as T;
}

export async function apiPost<T, B>(path: string, body: B): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const errBody = (await r.json().catch(() => ({}))) as ApiError;
    throw new ApiException(r.status, errBody);
  }
  return (await r.json()) as T;
}

// Re-export paths type so consumers can reference openapi route shapes if needed
export type { paths };
