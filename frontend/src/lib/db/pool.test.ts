import { afterEach, expect, it, vi } from "vitest";

const { created, on } = vi.hoisted(() => ({ created: vi.fn(), on: vi.fn() }));
vi.mock("pg", () => ({ Pool: class {
  constructor(config: unknown) { created(config); }
  on = on;
} }));
import { getAuthPool } from "./pool";

afterEach(() => {
  delete (globalThis as typeof globalThis & { alphaAuthPool?: unknown }).alphaAuthPool;
  vi.clearAllMocks();
});

it("shares one bounded pool and installs a sanitized idle error handler", () => {
  expect(getAuthPool()).toBe(getAuthPool());
  expect(created).toHaveBeenCalledOnce();
  expect(created.mock.calls[0][0]).toMatchObject({
    max: 3, connectionTimeoutMillis: 10_000,
  });
  expect(created.mock.calls[0][0]).not.toHaveProperty("statement_timeout");
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  on.mock.calls[0][1](new Error("sensitive connection string"));
  expect(JSON.stringify(error.mock.calls)).not.toContain("sensitive");
  error.mockRestore();
});
