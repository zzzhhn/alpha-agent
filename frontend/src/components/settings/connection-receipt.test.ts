import { afterEach, describe, expect, it, vi } from "vitest";
import { readLastConnectionTest, writeLastConnectionTest } from "./connection-state";

const credential = { userId: "41", provider: "openai", encryptedAt: "2026-11-26T11:00:00Z" };
const receipt = { at: "2026-11-26T11:05:00Z", ok: true, ...credential };

function stored(value: object) {
  vi.stubGlobal("window", { localStorage: { getItem: () => JSON.stringify(value) } });
}

afterEach(() => vi.unstubAllGlobals());

describe("connection test receipt", () => {
  it("does not reuse the global result across accounts, credential changes, or removal", () => {
    stored(receipt);
    expect(readLastConnectionTest({ ...credential, userId: "42" })).toBeNull();
    expect(readLastConnectionTest({ ...credential, provider: "kimi" })).toBeNull();
    expect(readLastConnectionTest({ ...credential, encryptedAt: "2026-11-26T11:06:00Z" })).toBeNull();
    expect(readLastConnectionTest(null)).toBeNull();
    expect(readLastConnectionTest(credential)).toEqual(receipt);
  });

  it("persists only the scope, time and result", () => {
    const setItem = vi.fn();
    vi.stubGlobal("window", { localStorage: { setItem } });
    const fromApi = { ...credential, api_key: "synthetic-key", base_url: "https://u:secret@example.test" };
    const written = writeLastConnectionTest(fromApi, true);
    expect(JSON.parse(setItem.mock.calls[0][1])).toEqual(written);
    expect(written).toEqual({ ...credential, ok: true, at: expect.any(String) });
  });

  it("ignores a legacy unscoped receipt", () => {
    stored({ at: receipt.at, ok: true });
    expect(readLastConnectionTest(credential)).toBeNull();
  });
});
