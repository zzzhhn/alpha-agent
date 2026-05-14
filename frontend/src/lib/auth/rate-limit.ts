// frontend/src/lib/auth/rate-limit.ts
//
// Node-only Postgres sliding-window rate limiter, backed by the
// auth_rate_limit table (V003). Chosen over Upstash Redis to avoid adding
// a new service at personal scale.
//
// The window is 1 minute, truncated to the minute boundary so concurrent
// requests in the same minute share one row. checkRateLimit() upserts the
// current-window row (incrementing hit_count) and returns allowed=false
// when the post-upsert count exceeds the per-action limit.
import type { Pool } from "pg";

/** Per-action limits, attempts per 1-minute window. */
export const RATE_LIMITS = {
  login: 5,
  register: 3,
  reset_request: 3,
} as const;

export type RateLimitAction = keyof typeof RATE_LIMITS;

export interface RateLimitResult {
  allowed: boolean;
  /** The per-action limit, surfaced so the caller can build a clear message. */
  limit: number;
}

/**
 * Upsert the current-minute window row for `<action>:<key>` and decide
 * whether this attempt is within the per-action limit.
 *
 * @param action  one of RATE_LIMITS' keys (login / register / reset_request)
 * @param key     the IP address or email this bucket is keyed on
 * @param pool    a pg Pool (passed in so tests can mock it)
 */
export async function checkRateLimit(
  action: RateLimitAction,
  key: string,
  pool: Pool,
): Promise<RateLimitResult> {
  const limit = RATE_LIMITS[action];
  const bucketKey = `${action}:${key}`;
  // Truncate "now" to the minute so all requests in the same minute hit one row.
  const result = await pool.query(
    `INSERT INTO auth_rate_limit (bucket_key, window_start, hit_count)
       VALUES ($1, date_trunc('minute', now()), 1)
     ON CONFLICT (bucket_key, window_start)
       DO UPDATE SET hit_count = auth_rate_limit.hit_count + 1
     RETURNING hit_count`,
    [bucketKey],
  );
  const hitCount = Number(result.rows[0]?.hit_count ?? 0);
  return { allowed: hitCount <= limit, limit };
}
