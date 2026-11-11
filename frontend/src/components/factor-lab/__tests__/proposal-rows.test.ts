import { describe, expect, it } from "vitest";
import { proposalRows } from "@/components/factor-lab/PendingProposalsSection";
import type { FactorProposal, FactorProposalGroup } from "@/lib/api/factor-lab";

const proposal = (id: number, expression: string) => ({ id, expression, status: "pending" }) as unknown as FactorProposal;
const group = (latest_id: number, ids: number[], has: boolean) => ({
  canonical_expression: "adv20", count: ids.length, proposal_ids: ids, latest_id,
  first_created_at: null, last_created_at: null, has_validation_evidence: has,
  best_mean_sharpe: null, best_ic_oos: null, latest_evidence: {},
}) as unknown as FactorProposalGroup;

describe("proposalRows", () => {
  it("shows one row per group using its latest member", () => {
    const rows = proposalRows([proposal(3, "adv20"), proposal(2, "adv20"), proposal(1, "x")], [group(3, [3, 2], true), group(1, [1], false)]);
    expect(rows.map((row) => [row.proposal.id, row.group?.count])).toEqual([[3, 2], [1, 1]]);
  });

  it("falls back to one row per proposal without grouping", () => {
    expect(proposalRows([proposal(1, "x"), proposal(2, "y")], null).map((row) => row.proposal.id)).toEqual([1, 2]);
  });
});
