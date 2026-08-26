"use client";

/**
 * PaperUi — small shared pieces for the /paper screen, styled to match the
 * BrainMiningPanel visual language (the platform's tm- baseline):
 *   - Metric: label-over-value, no card shell (KPI fix #1)
 *   - StatusChip: border-only 9px chip, GradeBadge geometry (fix #5)
 *   - Disclaimer: persistent honesty label (fix #6), lucide icon not emoji
 *   - TwoStepConfirm: inline two-step confirm, replaces window.confirm (fix #3)
 */
import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";

export function Metric({
  label,
  value,
  tone = "text-tm-fg",
}: {
  readonly label: string;
  readonly value: string;
  readonly tone?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-tm-mono text-xs uppercase tracking-[0.08em] text-tm-muted">
        {label}
      </span>
      <span className={`font-tm-mono text-[15px] font-semibold tabular-nums ${tone}`}>
        {value}
      </span>
    </div>
  );
}

const STATUS_CLS: Record<string, string> = {
  pending: "border-tm-warn text-tm-warn",
  filled: "border-tm-pos text-tm-pos",
  cancelled: "border-tm-rule text-tm-muted",
  expired: "border-tm-rule text-tm-muted",
  failed: "border-tm-neg text-tm-neg",
};

export function StatusChip({ status, label }: { readonly status: string; readonly label: string }) {
  const cls = STATUS_CLS[status] ?? "border-tm-rule text-tm-muted";
  return (
    <span className={`border px-1 py-px font-tm-mono text-xs font-bold uppercase ${cls}`}>
      {label}
    </span>
  );
}

export function Disclaimer() {
  const { locale } = useLocale();
  return (
    <p
      data-tour="sim-disclaimer"
      className="flex items-center gap-1.5 font-tm-mono text-xs leading-snug text-tm-muted"
    >
      <AlertTriangle className="h-3 w-3 shrink-0" strokeWidth={1.75} />
      {t(locale, "sim.disclaimer")}
    </p>
  );
}

type ConfirmState = "idle" | "confirm" | "sending" | "done" | "error";

/**
 * Two-step inline confirm — replaces window.confirm. Idle → click shows an
 * inline warning + [confirm]/[cancel]; confirming runs `onConfirm`; success
 * flashes a checkmark for 2s. Tone "neg" is for destructive actions (reset).
 */
export function TwoStepConfirm({
  idleLabel,
  warnText,
  doneText,
  onConfirm,
  tone = "neg",
}: {
  readonly idleLabel: string;
  readonly warnText: string;
  readonly doneText: string;
  readonly onConfirm: () => Promise<void>;
  readonly tone?: "neg" | "accent";
}) {
  const { locale } = useLocale();
  const [state, setState] = useState<ConfirmState>("idle");
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    setState("sending");
    setErr(null);
    try {
      await onConfirm();
      setState("done");
      setTimeout(() => setState("idle"), 2000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }

  if (state === "done") {
    return (
      <span className="inline-flex items-center gap-1.5 font-tm-mono text-xs text-tm-pos">
        <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
        {doneText}
      </span>
    );
  }

  if (state === "confirm" || state === "sending" || state === "error") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-tm-mono text-xs text-tm-muted">{warnText}</span>
        <TmButton
          variant={tone === "neg" ? "danger" : "secondary"}
          size="xs"
          onClick={() => void confirm()}
          loading={state === "sending"}
          loadingLabel={t(locale, "sim.confirm_btn")}
        >
          {t(locale, "sim.confirm_btn")}
        </TmButton>
        <TmButton
          variant="ghost"
          size="xs"
          onClick={() => setState("idle")}
        >
          {t(locale, "sim.cancel_btn")}
        </TmButton>
        {state === "error" && err ? (
          <span className="font-tm-mono text-xs text-tm-neg">{err}</span>
        ) : null}
      </div>
    );
  }

  return (
    <TmButton
      variant="secondary"
      size="xs"
      onClick={() => setState("confirm")}
      className="hover:border-tm-neg hover:text-tm-neg"
    >
      {idleLabel}
    </TmButton>
  );
}
