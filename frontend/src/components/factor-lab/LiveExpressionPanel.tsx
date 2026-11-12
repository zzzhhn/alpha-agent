"use client";
import { useAdminAccess } from "@/components/layout/SystemHealth";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Pencil, RotateCcw, X } from "lucide-react";
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
import { restorePresetExpression, setLiveExpression } from "@/lib/api/factor-lab";
import { parseFactorError } from "@/lib/factor-errors";
import { TmButton } from "@/components/tm/TmButton";
import { TmTextarea } from "@/components/tm/TmField";
import { TmDialog } from "@/components/tm/TmDialog";

/** Platform preset (signals/factor.py SHORT_TERM_FACTOR_EXPR). */
export const PRESET_FACTOR_EXPRESSION = "subtract(rank(ts_mean(returns, 12)), rank(ts_std(returns, 60)))";

export function isPresetExpression(expression: string): boolean {
  return expression.replace(/\s+/g, "") === PRESET_FACTOR_EXPRESSION.replace(/\s+/g, "");
}

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
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const zh = locale === "zh";
  const onPreset = isPresetExpression(expression);

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

  async function handleRestore() {
    setRestoring(true);
    setRestoreError(null);
    try {
      await restorePresetExpression();
      setConfirmRestore(false);
      router.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setRestoreError(parseFactorError(msg).summary || msg);
    } finally {
      setRestoring(false);
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
          <div className="flex items-center gap-1.5">
            {!onPreset ? (
              <TmButton
                variant="secondary"
                size="xs"
                onClick={() => setConfirmRestore(true)}
                disabled={!isAdmin}
                aria-haspopup="dialog"
              >
                <RotateCcw className="h-3 w-3" strokeWidth={1.75} />
                <span>{zh ? "恢复预设" : "Restore preset"}</span>
              </TmButton>
            ) : null}
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
          </div>
        ) : null}
      </div>

      {!editing ? (
        <>
          <pre className="overflow-x-auto rounded bg-tm-bg-2 p-2.5 font-mono text-xs text-tm-fg">
            {expression}
          </pre>
          <p className="font-tm-mono text-xs text-tm-muted">
            {onPreset
              ? (zh ? "平台预设：12 日动量减 60 日波动，读取每日行情。" : "Platform preset: 12-day momentum minus 60-day volatility, on live daily prices.")
              : (zh ? "自定义表达式：在仓库研究面板上计算，数据日期见股票页因子说明。" : "Custom expression: evaluated on the bundled research panel; see the factor note on stock pages for its data date.")}
          </p>
        </>
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

      <TmDialog
        open={confirmRestore}
        onClose={() => { if (!restoring) setConfirmRestore(false); }}
        title={zh ? "恢复平台预设表达式？" : "Restore the platform preset expression?"}
        closeLabel={zh ? "取消" : "Cancel"}
        className="max-w-[600px]"
      >
        <div className="space-y-3 text-sm leading-6 text-tm-fg-2">
          <div className="space-y-1">
            <p className="font-tm-mono text-xs text-tm-muted">{zh ? "当前" : "Current"}</p>
            <code className="block break-all font-mono text-xs text-tm-fg">{expression}</code>
            <p className="font-tm-mono text-xs text-tm-muted">{zh ? "恢复为" : "Restore to"}</p>
            <code className="block break-all font-mono text-xs text-tm-accent">{PRESET_FACTOR_EXPRESSION}</code>
          </div>
          <p>
            {zh
              ? "从下一次每日研究开始，因子信号改用预设表达式和每日行情计算。变更会写入“系统配置变更”，可再次手动改回。已发布的推荐快照、账户、持仓和机器人参数都不受影响。"
              : "From the next daily research run the factor signal uses the preset on live daily prices. The change is journaled in system configuration history and can be reverted manually. Published snapshots, accounts, positions and bot settings are unaffected."}
          </p>
          <p className="text-xs text-tm-muted">
            {zh
              ? "前瞻评估改用协议 quant-p0-v1.1.0-20261112，窗口 2026-11-13 → 2027-11-15；改动前后的样本不拼接。"
              : "Forward evaluation moves to protocol quant-p0-v1.1.0-20261112, window 2026-11-13 → 2027-11-15; samples before and after are not spliced."}
          </p>
          {restoreError ? (
            <p role="alert" className="font-tm-mono text-xs text-tm-neg">{restoreError}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <TmButton variant="secondary" size="sm" onClick={() => setConfirmRestore(false)} disabled={restoring}>
              {zh ? "取消" : "Cancel"}
            </TmButton>
            <TmButton variant="primary" size="sm" loading={restoring} onClick={() => void handleRestore()}>
              {zh ? "确认恢复预设" : "Restore preset"}
            </TmButton>
          </div>
        </div>
      </TmDialog>

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
