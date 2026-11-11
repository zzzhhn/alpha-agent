import { describe, expect, it } from "vitest";
import { alertMemberIds } from "@/lib/api/alertsFeed";

describe("alertMemberIds", () => {
  it("covers every member of a grouped alert", () => {
    expect(alertMemberIds({ id: 9, member_ids: [9, 7, 4] })).toEqual([9, 7, 4]);
  });

  it("falls back to the item id for legacy ungrouped rows", () => {
    expect(alertMemberIds({ id: 3 })).toEqual([3]);
    expect(alertMemberIds({ id: 3, member_ids: [] })).toEqual([3]);
  });
});
