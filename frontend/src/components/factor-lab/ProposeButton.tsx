"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { proposeFactors, type ProposeResult } from "@/lib/api/factor-lab";

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
        <div className="font-tm-mono text-[10px] text-tm-fg-2">
          Evaluated {result.evaluated}, proposed {result.proposed}
          {result.dormant && (
            <span className="ml-2 inline-flex items-center rounded border border-tm-warn/40 bg-tm-warn/10 px-1.5 py-0 font-tm-mono text-[9px] leading-[18px] text-tm-warn">
              dormant (insufficient history)
            </span>
          )}
        </div>
      )}

      {error && (
        <div className="font-tm-mono text-[10px] text-tm-neg">{error}</div>
      )}
    </div>
  );
}
