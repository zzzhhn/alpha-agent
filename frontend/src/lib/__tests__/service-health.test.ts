import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, ApiException } from "@/lib/api/client";
import { isHealthTimeout, readCachedServiceHealth, readSystemHealth, serializeServiceHealthCache } from "@/lib/service-health";
import type { ServiceState } from "@/components/tm/TmServiceStatus";

vi.mock("@/lib/api/client", async (original) => ({ ...await original<typeof import("@/lib/api/client")>(), apiGet: vi.fn() }));
const get = vi.mocked(apiGet);
beforeEach(() => { get.mockReset(); });
afterEach(() => { vi.useRealTimers(); });
function probes(health: unknown, pipeline: unknown) {
  get.mockImplementation((path) => {
    const value = path === "/api/_health" ? health : pipeline;
    return value instanceof Error ? Promise.reject(value) : Promise.resolve(value as never);
  });
}
describe("independent system-health observations", () => {
  const cases = [
    [{ db: "ok" }, { overall: "healthy" }, "healthy"],
    [{ db: "ok" }, { overall: "degraded" }, "degraded"],
    [{ db: "ok" }, new Error("timeout"), "partial"],
    [{ db: "ok" }, new ApiException(503, {}), "partial"],
    [new Error("offline"), { overall: "healthy" }, "unknown"],
    [new DOMException("cancelled", "AbortError"), new Error("timeout"), "unknown"],
    [new ApiException(401, {}), { overall: "healthy" }, "unknown"],
    [new ApiException(429, {}), { overall: "healthy" }, "unknown"],
    [new ApiException(502, {}), { overall: "healthy" }, "unavailable"],
    [new ApiException(504, { detail: "upstream timeout" }), { overall: "healthy" }, "unavailable"],
    [{ db: "down" }, new Error("failed"), "unavailable"],
    [{}, { overall: "healthy" }, "unknown"],
    [{ db: "ok" }, {}, "partial"],
  ] as const;
  cases.forEach(([health, pipeline, expected], index) => {
    it(`classifies observation ${index + 1} as ${expected}`, async () => {
      probes(health, pipeline);
      expect(await readSystemHealth()).toBe(expected);
      expect(get).toHaveBeenCalledTimes(2);
    });
  });
  it("recovers after a transient failure without retaining a false outage", async () => {
    probes(new Error("timeout"), { overall: "healthy" });
    expect(await readSystemHealth()).toBe("unknown");
    probes({ db: "ok" }, { overall: "degraded" });
    expect(await readSystemHealth()).toBe("degraded");
  });
});

describe("cold-start health timeout retry", () => {
  it("waits 15 seconds, retries connectivity once, and can recover", async () => {
    vi.useFakeTimers();
    let connectivityCalls = 0;
    get.mockImplementation((path) => {
      if (path !== "/api/_health") return Promise.resolve({ overall: "healthy" } as never);
      connectivityCalls += 1;
      return connectivityCalls === 1
        ? Promise.reject(new DOMException("deadline", "TimeoutError"))
        : Promise.resolve({ db: "ok" } as never);
    });
    const pending = readSystemHealth();
    await vi.advanceTimersByTimeAsync(14_999);
    expect(connectivityCalls).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toBe("healthy");
    expect(connectivityCalls).toBe(2);
    expect(get).toHaveBeenCalledTimes(3);
    expect(get).toHaveBeenNthCalledWith(3, "/api/_health", { timeoutMs: 12_000 });
  });

  it("returns unknown after a second timeout, without scheduling a third read", async () => {
    vi.useFakeTimers();
    probes(new DOMException("deadline", "TimeoutError"), { overall: "healthy" });
    const pending = readSystemHealth();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await pending).toBe("unknown");
    await vi.advanceTimersByTimeAsync(60_000);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("keeps a server error on the retry classified as unavailable", async () => {
    vi.useFakeTimers();
    get.mockRejectedValueOnce(new DOMException("deadline", "TimeoutError"))
      .mockResolvedValueOnce({ overall: "healthy" })
      .mockRejectedValueOnce(new ApiException(503, {}));
    const pending = readSystemHealth();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await pending).toBe("unavailable");
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("does not mistake offline, cancellation or an HTTP timeout response for a client timeout", () => {
    expect(isHealthTimeout(new DOMException("deadline", "TimeoutError"))).toBe(true);
    for (const error of [new Error("timeout"), new DOMException("cancelled", "AbortError"), new ApiException(504, {}), null]) {
      expect(isHealthTimeout(error)).toBe(false);
    }
  });
});

describe("session health cache", () => {
  const now = 1_800_000_000_000;

  it("round-trips every resolved state, including unknown, without caching checking", () => {
    const states: ServiceState[] = ["healthy", "degraded", "partial", "unavailable", "unknown"];
    for (const state of states) {
      expect(readCachedServiceHealth(serializeServiceHealthCache(state, now), now)).toBe(state);
    }
    expect(serializeServiceHealthCache("checking", now)).toBeNull();
  });

  it("accepts fresh entries and expires them at exactly two minutes", () => {
    const raw = serializeServiceHealthCache("healthy", now);
    expect(readCachedServiceHealth(raw, now + 119_999)).toBe("healthy");
    expect(readCachedServiceHealth(raw, now + 120_000)).toBeNull();
    expect(readCachedServiceHealth(raw, now + 180_000)).toBeNull();
    expect(readCachedServiceHealth(raw, now - 1)).toBeNull();
  });

  it("ignores malformed storage, invalid states and missing timestamps", () => {
    for (const raw of [null, "", "oops", "null", "[]", "{}", '{"state":"healthy"}',
      JSON.stringify({ state: "checking", timestamp: now }),
      JSON.stringify({ state: "invented", timestamp: now }),
      JSON.stringify({ state: "healthy", timestamp: String(now) }),
      JSON.stringify({ state: "healthy", timestamp: null })]) {
      expect(readCachedServiceHealth(raw, now)).toBeNull();
    }
  });
});
