// frontend/src/app/(auth)/reset-password/__tests__/actions.test.ts
//
// resetPasswordAction talks to Postgres (pg Pool). Mocked. password.ts is
// NOT mocked, the test seeds a real bcrypt hash of the code into the
// fake "code row" so verifyPassword exercises the real comparison.
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.hoisted ensures mockQuery is available when the vi.mock factory runs
// (factories are hoisted to the top of the file by vitest transform).
const { mockQuery } = vi.hoisted(() => ({ mockQuery: vi.fn() }));

vi.mock("pg", () => {
  function Pool() {
    return { query: mockQuery };
  }
  return { Pool };
});

import { resetPasswordAction } from "@/app/(auth)/reset-password/actions";
import { hashPassword, verifyPassword } from "@/lib/auth/password";

function formDataOf(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

const FUTURE = new Date(Date.now() + 10 * 60_000).toISOString();
const PAST = new Date(Date.now() - 10 * 60_000).toISOString();

beforeEach(() => {
  mockQuery.mockReset();
});

describe("resetPasswordAction", () => {
  it("rejects a wrong code (no matching unused unexpired row found)", async () => {
    // First query: fresh-row lookup returns empty.
    // Second query: fallback any-row lookup also returns empty.
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({ rows: [], rowCount: 0 });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "000000", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("wrong_code");
  });

  it("rejects a code whose hash does not verify (wrong code, row exists)", async () => {
    const otherHash = await hashPassword("999999");
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: 1, code_hash: otherHash, expires_at: FUTURE, used: false }],
      rowCount: 1,
    });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("wrong_code");
  });

  it("rejects an expired code", async () => {
    const codeHash = await hashPassword("123456");
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({
        rows: [{ id: 1, code_hash: codeHash, expires_at: PAST, used: false }],
        rowCount: 1,
      });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("expired_code");
  });

  it("rejects an already-used code", async () => {
    const codeHash = await hashPassword("123456");
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({
        rows: [{ id: 1, code_hash: codeHash, expires_at: FUTURE, used: true }],
        rowCount: 1,
      });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("used_code");
  });

  it("rejects a short new password via zod", async () => {
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "short" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("succeeds: updates users.password_hash and marks the code used", async () => {
    const codeHash = await hashPassword("123456");
    mockQuery
      .mockResolvedValueOnce({
        rows: [{ id: 1, code_hash: codeHash, expires_at: FUTURE, used: false }],
        rowCount: 1,
      })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });

    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(true);

    const updateParams = mockQuery.mock.calls[1][1] as string[];
    expect(updateParams).not.toContain("longenough1");
    const newHash = updateParams.find((p) => p.startsWith("$2"));
    expect(await verifyPassword("longenough1", newHash as string)).toBe(true);

    const usedSql = mockQuery.mock.calls[2][0] as string;
    expect(usedSql).toMatch(/UPDATE password_reset_codes/i);
    expect(usedSql).toMatch(/used = true/i);
  });
});
