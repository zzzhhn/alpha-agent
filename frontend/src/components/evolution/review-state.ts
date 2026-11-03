export function pendingReviewCounts(
  policy: readonly { status: string }[] | null,
  methodology: readonly { status: string }[] | null,
) {
  const count = (items: typeof policy) =>
    items?.filter((item) => item.status === "pending").length ?? null;
  const policyCount = count(policy);
  const methodologyCount = count(methodology);
  return {
    policy: policyCount,
    methodology: methodologyCount,
    total: policyCount === null || methodologyCount === null ? null : policyCount + methodologyCount,
    known: (policyCount ?? 0) + (methodologyCount ?? 0),
  };
}

export const EVOLUTION_PAGE_SIZE = 5;

export function evolutionPage<T>(rows: readonly T[], requestedPage: number) {
  const page = Math.max(1, Math.min(requestedPage, Math.ceil(rows.length / EVOLUTION_PAGE_SIZE)));
  return { page, visible: rows.slice((page - 1) * EVOLUTION_PAGE_SIZE, page * EVOLUTION_PAGE_SIZE) };
}
