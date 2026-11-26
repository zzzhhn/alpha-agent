import { describe, expect, it } from "vitest";
import { parseOrderQuantity } from "../SimOrderForm";

describe("simulation order quantity", () => {
  it.each([
    ["100", 100],
    ["1e2", 100],
    ["2.147483647e9", 2_147_483_647],
  ])("reads %s as %i shares", (input, shares) => {
    expect(parseOrderQuantity(input)).toBe(shares);
  });

  it.each(["", "0", "-1", "1.5", "1e-2", "1e", "2147483648", "9007199254740992"])(
    "rejects %j",
    (input) => {
      expect(parseOrderQuantity(input)).toBeNull();
    },
  );
});
