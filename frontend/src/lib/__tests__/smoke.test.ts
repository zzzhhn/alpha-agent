// frontend/src/lib/__tests__/smoke.test.ts
// Trivial smoke test, proves the vitest runner is wired and executing.
// Real unit tests arrive in tasks B2, C1, D1, D2.
import { describe, it, expect } from "vitest";

describe("vitest runner smoke", () => {
  it("executes a trivial assertion", () => {
    expect(1 + 1).toBe(2);
  });
});
