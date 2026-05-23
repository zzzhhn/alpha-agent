"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { proposeFactors, type ProposeResult } from "@/lib/api/factor-lab";

function _explain(r: ProposeResult): string {
  if (r.dormant) {
    return "Insufficient daily_prices history for the validator (or cost-guard tripped). The LLM was not called; no tokens spent.";
  }
  if (r.evaluated === 0) {
    return "The LLM returned no usable proposals (JSON parse or empty list). Try again.";
  }
  if (r.proposed === 0) {
    return `${r.evaluated} candidate(s) evaluated; none beat the current expression's deflated Sharpe baseline, so nothing was queued. This is expected when the LLM cannot find genuine alpha against the live factor.`;
  }
  return `${r.proposed} candidate(s) queued as pending below. Review and Approve to apply.`;
}

export function ProposeButton({ n = 5 }: { n?: number }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ProposeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await proposeFactors(n);
      setResult(r);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handleClick}
        disabled={loading}
        className="inline-flex w-fit items-center gap-2 rounded border border-tm-accent/40 bg-tm-accent/10 px-3 py-1.5 font-tm-mono text-[11px] text-tm-accent transition-opacity disabled:opacity-50 enabled:hover:bg-tm-accent/20"
      >
        {loading ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            <span>Proposing... (this may take 30 to 60 s)</span>
          </>
        ) : (
          <span>Propose factors (n={n})</span>
        )}
      </button>

      {result && (
        <div className="flex flex-col gap-1 rounded border border-tm-line bg-tm-card px-3 py-2 text-sm">
          <div className="flex items-baseline gap-2">
            <span className="text-base font-semibold text-tm-fg-1">
              {result.proposed} / {result.evaluated} proposed
            </span>
            {result.dormant && (
              <span className="inline-flex items-center rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-0.5 text-xs text-tm-warn">
                dormant
              </span>
            )}
          </div>
          <p className="text-xs text-tm-fg-2">
            {_explain(result)}
          </p>
        </div>
      )}

      {error && (
        <div className="rounded border border-tm-neg/40 bg-tm-neg/10 px-3 py-2 text-sm text-tm-neg">
          {error}
        </div>
      )}
    </div>
  );
}
