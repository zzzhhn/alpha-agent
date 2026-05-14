// frontend/src/lib/auth/__tests__/password.test.ts
import { describe, it, expect } from "vitest";
import { hashPassword, verifyPassword } from "@/lib/auth/password";

describe("password.ts - bcryptjs wrapper", () => {
  it("hashPassword produces a hash that differs from the plaintext", async () => {
    const hash = await hashPassword("hunter2-correct-horse");
    expect(hash).not.toBe("hunter2-correct-horse");
    expect(hash.length).toBeGreaterThan(20);
    // bcrypt hashes start with $2 (the algorithm identifier).
    expect(hash.startsWith("$2")).toBe(true);
  });

  it("verifyPassword round-trips: the original plaintext verifies true", async () => {
    const hash = await hashPassword("hunter2-correct-horse");
    expect(await verifyPassword("hunter2-correct-horse", hash)).toBe(true);
  });

  it("verifyPassword returns false for a wrong password", async () => {
    const hash = await hashPassword("hunter2-correct-horse");
    expect(await verifyPassword("wrong-password", hash)).toBe(false);
  });

  it("two hashes of the same plaintext differ (per-hash salt)", async () => {
    const a = await hashPassword("same-input");
    const b = await hashPassword("same-input");
    expect(a).not.toBe(b);
    expect(await verifyPassword("same-input", a)).toBe(true);
    expect(await verifyPassword("same-input", b)).toBe(true);
  });
});
