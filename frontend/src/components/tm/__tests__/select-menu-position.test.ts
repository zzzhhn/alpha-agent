import { describe, expect, it } from "vitest";
import { tmMenuVerticalPosition } from "../TmSelectMenu";

describe("select menu placement", () => {
  it("keeps short menus below when they fit", () => {
    expect(tmMenuVerticalPosition(669, 697, 875, 90)).toEqual({ top: 701, maxHeight: 166 });
  });
  it("attaches an upward menu to its real height", () => {
    expect(tmMenuVerticalPosition(800, 828, 875, 90)).toEqual({ top: 706, maxHeight: 288 });
  });
  it("bounds long menus within the available viewport", () => {
    expect(tmMenuVerticalPosition(180, 208, 400, 900)).toEqual({ top: 212, maxHeight: 180 });
  });
});
