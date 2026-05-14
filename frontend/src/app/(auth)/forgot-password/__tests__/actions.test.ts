// frontend/src/app/(auth)/forgot-password/__tests__/actions.test.ts
//
// forgotPasswordAction talks to Postgres (pg Pool) and sends mail
// (nodemailer). Both are mocked. password.ts is NOT mocked; the test
// asserts the stored code is a real bcrypt hash, not the plaintext.
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.hoisted ensures these variables are available when vi.mock factories
// run (factories are hoisted to the top of the file by vitest transform).
const { mockQuery, mockSendMail, mockCheckRateLimit } = vi.hoisted(() => ({
  mockQuery: vi.fn(),
  mockSendMail: vi.fn(async () => ({ messageId: "fake" })),
  mockCheckRateLimit: vi.fn(async () => ({ allowed: true, limit: 3 })),
}));

vi.mock("pg", () => {
  function Pool() {
    return { query: mockQuery };
  }
  return { Pool };
});

vi.mock("nodemailer", () => ({
  default: { createTransport: vi.fn(() => ({ sendMail: mockSendMail })) },
  createTransport: vi.fn(() => ({ sendMail: mockSendMail })),
}));

vi.mock("@/lib/auth/rate-limit", () => ({
  checkRateLimit: mockCheckRateLimit,
  RATE_LIMITS: { login: 5, register: 3, reset_request: 3 },
}));

import { forgotPasswordAction } from "@/app/(auth)/forgot-password/actions";
import { verifyPassword } from "@/lib/auth/password";

function formDataOf(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

beforeEach(() => {
  mockQuery.mockReset();
  mockSendMail.mockReset();
  mockSendMail.mockResolvedValue({ messageId: "fake" });
  mockCheckRateLimit.mockReset();
  mockCheckRateLimit.mockResolvedValue({ allowed: true, limit: 3 });
});

describe("forgotPasswordAction", () => {
  it("returns the same ok:true response when the email exists", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [{ id: 5 }], rowCount: 1 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });
    const result = await forgotPasswordAction(formDataOf({ email: "real@b.com" }));
    expect(result.ok).toBe(true);
  });

  it("returns the SAME ok:true response when the email does NOT exist", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });
    const result = await forgotPasswordAction(formDataOf({ email: "ghost@b.com" }));
    expect(result.ok).toBe(true);
  });

  it("stores the code HASHED, never as plaintext", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [{ id: 5 }], rowCount: 1 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });
    await forgotPasswordAction(formDataOf({ email: "real@b.com" }));

    const insertCall = mockQuery.mock.calls[1];
    const insertParams = insertCall[1] as string[];
    const codeHashParam = insertParams.find((p) => p.startsWith("$2"));
    expect(codeHashParam).toBeDefined();

    const mailArg = (mockSendMail.mock.calls[0] as unknown as [{ text?: string }])[0];
    const plaintextCode = (mailArg.text ?? "").match(/\d{6}/)?.[0];
    expect(plaintextCode).toMatch(/^\d{6}$/);
    expect(insertParams).not.toContain(plaintextCode);
    expect(await verifyPassword(plaintextCode as string, codeHashParam as string)).toBe(true);
  });

  it("denies when the reset_request rate limit is exceeded", async () => {
    mockCheckRateLimit.mockResolvedValueOnce({ allowed: false, limit: 3 });
    const result = await forgotPasswordAction(formDataOf({ email: "real@b.com" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("rate_limited");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("rejects a malformed email via zod", async () => {
    const result = await forgotPasswordAction(formDataOf({ email: "not-an-email" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
  });
});
