"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2, Pencil, X } from "lucide-react";
import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";
import {
  extractOperands,
  extractOps,
  isAllowedOp,
  isAllowedOperand,
  suggestOp,
  suggestOperand,
} from "@/lib/factor-spec";
import { setLiveExpression } from "@/lib/api/factor-lab";
import { parseFactorError } from "@/lib/factor-errors";

interface LiveExpressionPanelProps {
  readonly locale: Locale;
  readonly expression: string;
  readonly deployedAgoDays?: number | null;
}

export function LiveExpressionPanel({
  locale,
  expression,
  deployedAgoDays,
}: LiveExpressionPanelProps) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(expression);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Validate ops + operands the same way BacktestFormSticky does (Fix A+D).
  // ALLOWED_OPERANDS in factor-spec.ts permits operator names too (factor_ast
  // matches them as ast.Name), so filter via isAllowedOperand || isAllowedOp.
  const unknownOps = useMemo(
    () => extractOps(draft).filter((op) => !isAllowedOp(op)),
    [draft],
  );
  const unknownOperands = useMemo(
    () =>
      extractOperands(draft).filter(
        (o) => !isAllowedOperand(o) && !isAllowedOp(o),
      ),
    [draft],
  );
  const hasValidationIssues =
    unknownOps.length > 0 || unknownOperands.length > 0;
  const canSave =
    draft.trim().length > 0 && !hasValidationIssues && draft !== expression;

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await setLiveExpression(draft.trim());
      setEditing(false);
      router.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setSaveError(parseFactorError(msg).summary || msg);
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setDraft(expression);
    setSaveError(null);
    setEditing(false);
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
          {t(locale, "factorLab.decision.liveExpression")}
        </div>
        {!editing ? (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="flex items-center gap-1 rounded border border-tm-rule px-1.5 py-0.5 font-tm-mono text-[10px] text-tm-muted hover:bg-tm-bg-3 hover:text-tm-fg"
            aria-label={t(locale, "factorLab.decision.editLive")}
          >
            <Pencil className="h-3 w-3" strokeWidth={1.75} />
            <span>{t(locale, "factorLab.decision.editLive")}</span>
          </button>
        ) : null}
      </div>

      {!editing ? (
        <pre className="overflow-x-auto rounded bg-tm-bg-2 p-2.5 font-mono text-[11px] text-tm-fg">
          {expression}
        </pre>
      ) : (
        <div className="flex flex-col gap-1.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            rows={3}
            className="w-full resize-y rounded bg-tm-bg-2 p-2.5 font-mono text-[11px] text-tm-fg outline-none focus:ring-1 focus:ring-tm-accent"
            aria-invalid={hasValidationIssues || undefined}
          />
          {hasValidationIssues ? (
            <div
              role="alert"
              className="rounded border border-tm-warn/40 bg-tm-warn/5 px-2 py-1.5 font-tm-mono text-[10px] text-tm-warn"
            >
              {unknownOps.map((op) => {
                const sug = suggestOp(op);
                return (
                  <div key={`op-${op}`}>
                    {t(locale, "backtest.form.unknownOp")}: <code>{op}</code>
                    {sug ? (
                      <>
                        {" "}
                        {t(locale, "backtest.form.didYouMean")}{" "}
                        <code className="text-tm-pos">{sug}</code>
                      </>
                    ) : null}
                  </div>
                );
              })}
              {unknownOperands.map((o) => {
                const sug = suggestOperand(o);
                return (
                  <div key={`opd-${o}`}>
                    {t(locale, "backtest.form.unknownOperand")}: <code>{o}</code>
                    {sug ? (
                      <>
                        {" "}
                        {t(locale, "backtest.form.didYouMean")}{" "}
                        <code className="text-tm-pos">{sug}</code>
                      </>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
          {saveError ? (
            <div className="rounded border border-tm-neg/40 bg-tm-neg/10 px-2 py-1.5 font-tm-mono text-[10px] text-tm-neg">
              {t(locale, "factorLab.decision.saveFailed")}: {saveError}
            </div>
          ) : null}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave || saving}
              className="inline-flex items-center gap-1 rounded border border-tm-accent/60 bg-tm-accent px-2 py-0.5 font-tm-mono text-[10px] text-tm-bg transition-opacity disabled:opacity-40 enabled:hover:bg-tm-accent/90"
            >
              {saving ? (
                <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
              ) : (
                <Check className="h-3 w-3" strokeWidth={1.75} />
              )}
              <span>{t(locale, "factorLab.decision.saveLive")}</span>
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded border border-tm-rule bg-tm-bg-3 px-2 py-0.5 font-tm-mono text-[10px] text-tm-fg-2 transition-opacity disabled:opacity-40 enabled:hover:bg-tm-bg-3/60"
            >
              <X className="h-3 w-3" strokeWidth={1.75} />
              <span>{t(locale, "factorLab.decision.cancelLive")}</span>
            </button>
          </div>
        </div>
      )}

      {deployedAgoDays != null ? (
        <div className="font-tm-mono text-[10px] text-tm-muted">
          {t(locale, "factorLab.decision.deployedAgo").replace(
            "{n}",
            String(deployedAgoDays),
          )}
        </div>
      ) : null}
    </div>
  );
}
