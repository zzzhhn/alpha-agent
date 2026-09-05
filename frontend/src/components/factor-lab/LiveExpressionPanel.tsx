"use client";
import { useAdminAccess } from "@/components/layout/SystemHealth";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Pencil, X } from "lucide-react";
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
import { TmButton } from "@/components/tm/TmButton";
import { TmTextarea } from "@/components/tm/TmField";

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
  const isAdmin = useAdminAccess();
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
        <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
          {t(locale, "factorLab.decision.liveExpression")}
        </div>
        {!editing ? (
          <TmButton
            variant="secondary"
            size="xs"
            onClick={() => setEditing(true)}
            disabled={!isAdmin}
            aria-label={t(locale, "factorLab.decision.editLive")}
          >
            <Pencil className="h-3 w-3" strokeWidth={1.75} />
            <span>{t(locale, "factorLab.decision.editLive")}</span>
          </TmButton>
        ) : null}
      </div>

      {!editing ? (
        <pre className="overflow-x-auto rounded bg-tm-bg-2 p-2.5 font-mono text-xs text-tm-fg">
          {expression}
        </pre>
      ) : (
        <div className="flex flex-col gap-1.5">
          <TmTextarea
            value={draft}
            onChange={setDraft}
            spellCheck={false}
            rows={3}
            aria-invalid={hasValidationIssues || undefined}
            textareaClassName="min-h-0 resize-y rounded bg-tm-bg-2 p-2.5 font-mono text-xs text-tm-fg outline-none focus:ring-1 focus:ring-tm-accent"
          />
          {hasValidationIssues ? (
            <div
              role="alert"
              className="rounded border border-tm-warn/40 bg-tm-warn/5 px-2 py-1.5 font-tm-mono text-xs text-tm-warn"
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
            <div className="rounded border border-tm-neg/40 bg-tm-neg/10 px-2 py-1.5 font-tm-mono text-xs text-tm-neg">
              {t(locale, "factorLab.decision.saveFailed")}: {saveError}
            </div>
          ) : null}
          <div className="flex items-center gap-2">
            <TmButton
              variant="primary"
              size="xs"
              onClick={handleSave}
              disabled={!canSave || saving}
              loading={saving}
              loadingLabel={t(locale, "factorLab.decision.saveLive")}
            >
              <Check className="h-3 w-3" strokeWidth={1.75} />
              <span>{t(locale, "factorLab.decision.saveLive")}</span>
            </TmButton>
            <TmButton
              variant="secondary"
              size="xs"
              onClick={handleCancel}
              disabled={saving}
            >
              <X className="h-3 w-3" strokeWidth={1.75} />
              <span>{t(locale, "factorLab.decision.cancelLive")}</span>
            </TmButton>
          </div>
        </div>
      )}

      {deployedAgoDays != null ? (
        <div className="font-tm-mono text-xs text-tm-muted">
          {t(locale, "factorLab.decision.deployedAgo").replace(
            "{n}",
            String(deployedAgoDays),
          )}
        </div>
      ) : null}
    </div>
  );
}
