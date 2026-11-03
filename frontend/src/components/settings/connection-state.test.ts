import { describe, expect, it } from "vitest";
import type { ByokGetResponse } from "@/lib/api/user";
import { PROVIDER_PRESETS } from "@/lib/byok";
import { savedConnectionMatches } from "./connection-state";

const saved: ByokGetResponse = {
  provider: "openai",
  last4: "1234",
  base_url: null,
  model: null,
  encrypted_at: "2026-11-03T00:00:00Z",
  last_used_at: null,
};
const { defaultBase, defaultModel } = PROVIDER_PRESETS.openai;

describe("savedConnectionMatches", () => {
  it("does not treat absent metadata as a saved default connection", () => {
    expect(savedConnectionMatches(null, "openai", defaultBase, defaultModel)).toBe(false);
  });

  it("uses provider defaults for missing saved endpoint and model", () => {
    expect(savedConnectionMatches(saved, "openai", defaultBase, defaultModel)).toBe(true);
  });

  it("rejects a different provider even with identical coordinates", () => {
    expect(savedConnectionMatches(saved, "kimi", defaultBase, defaultModel)).toBe(false);
  });

  it("requires the saved custom endpoint to match", () => {
    const base_url = "https://gateway.example.test/v1";
    expect(savedConnectionMatches({ ...saved, base_url }, "openai", base_url, defaultModel)).toBe(true);
    expect(savedConnectionMatches({ ...saved, base_url }, "openai", defaultBase, defaultModel)).toBe(false);
  });

  it("requires the saved custom model to match", () => {
    const model = "research-model";
    expect(savedConnectionMatches({ ...saved, model }, "openai", defaultBase, model)).toBe(true);
    expect(savedConnectionMatches({ ...saved, model }, "openai", defaultBase, defaultModel)).toBe(false);
  });
});
