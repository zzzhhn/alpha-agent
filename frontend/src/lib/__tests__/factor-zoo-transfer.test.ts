import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.stubGlobal("window", {
  localStorage: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
  },
});

const zoo = await import("@/lib/factor-zoo");

describe("factor zoo JSON transfer", () => {
  beforeEach(() => store.clear());

  it("round-trips entries through export and import", () => {
    zoo.addToZoo({ name: "Momentum", expression: "rank(ts_mean(returns, 12))", hypothesis: "h" });
    const backup = zoo.exportZooJson();
    zoo.clearZoo();
    expect(zoo.importZooJson(backup)).toEqual({ added: 1, skipped: 0 });
    expect(zoo.listZoo().map((e) => e.expression)).toEqual(["rank(ts_mean(returns, 12))"]);
  });

  it("never overwrites an existing expression and skips malformed items", () => {
    zoo.addToZoo({ name: "Local", expression: "rank(close)", hypothesis: "" });
    const result = zoo.importZooJson(JSON.stringify({ entries: [
      { name: "Old copy", expression: "rank(close)" },
      { name: "No expression" },
      { name: "New", expression: "rank(volume)", savedAt: "2026-01-01T00:00:00Z" },
    ] }));
    expect(result).toEqual({ added: 1, skipped: 2 });
    expect(zoo.listZoo().find((e) => e.expression === "rank(close)")?.name).toBe("Local");
  });

  it("rejects non-JSON without changing the library", () => {
    zoo.addToZoo({ name: "Keep", expression: "rank(open)", hypothesis: "" });
    expect(() => zoo.importZooJson("not json")).toThrow("invalid_json");
    expect(zoo.listZoo()).toHaveLength(1);
  });
});
