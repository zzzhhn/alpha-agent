// frontend/src/app/(auth)/register/__tests__/actions.test.ts
//
// The registration action talks to Postgres via a module-level pg Pool.
// We mock the "pg" module so Pool() returns a controllable fake, and mock
// rate-limit.ts so the limiter never blocks unless a test wants it to.
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.hoisted ensures these variables are available when vi.mock factories
// run (factories are hoisted to the top of the file by vitest transform).
const { mockQuery, mockCheckRateLimit } = vi.hoisted(() => ({
  mockQuery: vi.fn(),
  mockCheckRateLimit: vi.fn(),
}));

// --- mock the pg Pool ---------------------------------------------------
// Pool is used as `new Pool(...)` so we provide a real class constructor.
vi.mock("pg", () => {
  function Pool() {
    return { query: mockQuery };
  }
  return { Pool };
});

// --- mock the rate limiter (default: allow) -----------------------------
vi.mock("@/lib/auth/rate-limit", () => ({
  checkRateLimit: mockCheckRateLimit,
  RATE_LIMITS: { login: 5, register: 3, reset_request: 3 },
}));

// password.ts is NOT mocked - we want the real bcryptjs so the test can
// assert the INSERT received a real hash, not the plaintext.
import { registerAction } from "@/app/(auth)/register/actions";
import { verifyPassword } from "@/lib/auth/password";

function formDataOf(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

beforeEach(() => {
  mockQuery.mockReset();
  mockCheckRateLimit.mockReset();
  mockCheckRateLimit.mockResolvedValue({ allowed: true, limit: 3 });
});

describe("registerAction", () => {
  it("rejects a password shorter than 8 chars (zod)", async () => {
    const result = await registerAction(
      formDataOf({ email: "a@b.com", password: "short", confirmPassword: "short" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("rejects when confirmPassword does not match", async () => {
    const result = await registerAction(
      formDataOf({
        email: "a@b.com",
        password: "longenough1",
        confirmPassword: "different123",
      }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
  });

  it("rejects a duplicate email", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 7 }], rowCount: 1 });
    const result = await registerAction(
      formDataOf({
        email: "taken@b.com",
        password: "longenough1",
        confirmPassword: "longenough1",
      }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("email_taken");
    expect(mockQuery).toHaveBeenCalledOnce();
  });

  it("denies when the rate limit is exceeded", async () => {
    mockCheckRateLimit.mockResolvedValueOnce({ allowed: false, limit: 3 });
    const result = await registerAction(
      formDataOf({
        email: "a@b.com",
        password: "longenough1",
        confirmPassword: "longenough1",
      }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("rate_limited");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("hashes the password before the INSERT and succeeds", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({ rows: [{ id: 99 }], rowCount: 1 });

    const result = await registerAction(
      formDataOf({
        email: "new@b.com",
        password: "longenough1",
        confirmPassword: "longenough1",
      }),
    );
    expect(result.ok).toBe(true);

    const insertCall = mockQuery.mock.calls[1];
    const insertParams = insertCall[1] as (string | null)[];
    expect(insertParams).not.toContain("longenough1");
    // Filter out null (the name field) before calling startsWith.
    const hashParam = insertParams.filter((p): p is string => p !== null).find((p) => p.startsWith("$2"));
    expect(hashParam).toBeDefined();
    expect(await verifyPassword("longenough1", hashParam as string)).toBe(true);
  });
});
