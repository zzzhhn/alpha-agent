import { describe, expect, it } from "vitest";

import { formatUtc8DateTime } from "../format-datetime";

describe("formatUtc8DateTime", () => {
  it("renders the same explicit UTC+8 value in every runtime", () => {
    expect(formatUtc8DateTime("2026-08-03T22:55:00Z")).toBe(
      "08/04 06:55 UTC+8",
    );
  });

  it("supports full audit timestamps and honest fallbacks", () => {
    expect(
      formatUtc8DateTime("2026-07-22T23:00:17Z", {
        year: "numeric",
        seconds: true,
      }),
    ).toBe("2026/07/23 07:00:17 UTC+8");
    expect(formatUtc8DateTime("not-a-date", { fallback: "invalid" })).toBe(
      "invalid",
    );
    expect(formatUtc8DateTime(null)).toBe("—");
  });
});
