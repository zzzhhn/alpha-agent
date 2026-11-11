import { describe, expect, it } from "vitest";
import { connectionTestStatus, providerDisplay } from "./connection-state";
import { changeFieldLabel } from "./ChangeLog";

describe("settings truthfulness", () => {
  it("labels an OpenAI-compatible endpoint on another host", () => {
    expect(providerDisplay("openai", "https://api.kimi.com/coding/v1", true)).toBe("OpenAI 兼容接口 · api.kimi.com");
    expect(providerDisplay("openai", "https://api.openai.com/v1", true)).toBe("OpenAI");
    expect(providerDisplay("openai", null, false)).toBe("OpenAI");
  });

  it("shows the last test result instead of a permanent unconfirmed", () => {
    expect(connectionTestStatus({ kind: "idle" }, null, true)).toEqual({ value: "未测试", tone: "default" });
    expect(connectionTestStatus({ kind: "idle" }, { at: "2026-11-11T02:00:00Z", ok: false }, true).tone).toBe("negative");
    expect(connectionTestStatus({ kind: "ok" }, null, false)).toEqual({ value: "Passed", tone: "positive" });
  });

  it("translates known config fields and keeps unknown keys", () => {
    expect(changeFieldLabel("factor.custom_expression", true)).toBe("线上因子表达式");
    expect(changeFieldLabel("something.else", true)).toBe("something.else");
  });
});
