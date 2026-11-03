import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, ApiException } from "@/lib/api/client";
import { readSystemHealth } from "@/lib/service-health";

vi.mock("@/lib/api/client", async (original) => ({ ...await original<typeof import("@/lib/api/client")>(), apiGet: vi.fn() }));
const get = vi.mocked(apiGet);
beforeEach(() => { get.mockReset(); });
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
    [new DOMException("deadline", "TimeoutError"), new Error("timeout"), "unknown"],
    [new ApiException(401, {}), { overall: "healthy" }, "unknown"],
    [new ApiException(429, {}), { overall: "healthy" }, "unknown"],
    [new ApiException(502, {}), { overall: "healthy" }, "unavailable"],
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
