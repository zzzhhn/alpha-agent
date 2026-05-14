// frontend/src/lib/auth/__tests__/rate-limit.test.ts
//
// rate-limit.ts talks to Postgres. The unit test mocks the pg Pool the
// same way the backend tests mock asyncpg in tests/api/: a fake pool whose
// query() returns a controlled rows payload, so we exercise the
// allow/deny branching without a live database.
import { describe, it, expect, vi } from "vitest";
import { checkRateLimit, RATE_LIMITS } from "@/lib/auth/rate-limit";

// A fake pg Pool: query() returns whatever the test queues up.
function fakePool(hitCountAfterUpsert: number) {
  return {
    query: vi.fn(async () => ({
      rows: [{ hit_count: hitCountAfterUpsert }],
      rowCount: 1,
    })),
  };
}

describe("rate-limit.ts - checkRateLimit", () => {
  it("exposes per-action limits as consts", () => {
    expect(RATE_LIMITS.login).toBe(5);
    expect(RATE_LIMITS.register).toBe(3);
    expect(RATE_LIMITS.reset_request).toBe(3);
  });

  it("allows when the post-upsert hit_count is at or under the limit", async () => {
    // login limit is 5; a hit_count of 5 is the 5th attempt, still allowed.
    const pool = fakePool(5);
    const result = await checkRateLimit("login", "1.2.3.4", pool as never);
    expect(result.allowed).toBe(true);
    expect(pool.query).toHaveBeenCalledOnce();
  });

  it("denies when the post-upsert hit_count exceeds the limit", async () => {
    // login limit is 5; a hit_count of 6 means this attempt is over.
    const pool = fakePool(6);
    const result = await checkRateLimit("login", "1.2.3.4", pool as never);
    expect(result.allowed).toBe(false);
  });

  it("denies a register attempt over the register limit of 3", async () => {
    const pool = fakePool(4);
    const result = await checkRateLimit("register", "1.2.3.4", pool as never);
    expect(result.allowed).toBe(false);
  });

  it("builds the bucket_key as <action>:<key>", async () => {
    const pool = fakePool(1);
    await checkRateLimit("reset_request", "user@example.com", pool as never);
    // pool.query is called as query(sql, params); params is the second argument.
    const callArgs = pool.query.mock.calls[0] as unknown as [string, string[]];
    const params = callArgs[1];
    expect(params[0]).toBe("reset_request:user@example.com");
  });
});
