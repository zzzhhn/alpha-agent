"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { SignalForm, type SignalParams } from "@/components/signal/SignalForm";
import { TopBottomTable } from "@/components/signal/TopBottomTable";
import { ICTimeseriesChart } from "@/components/signal/ICTimeseriesChart";
import { ExposureChart } from "@/components/signal/ExposureChart";
import { signalToday, signalIcTimeseries, signalExposure } from "@/lib/api";
import type {
  SignalSpec,
  SignalTodayResponse,
  ICTimeseriesResponse,
  ExposureResponse,
} from "@/lib/types";

export default function SignalPage() {
  const { locale } = useLocale();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topN, setTopN] = useState(10);
  const [today, setToday] = useState<SignalTodayResponse | null>(null);
  const [icTs, setIcTs] = useState<ICTimeseriesResponse | null>(null);
  const [exposure, setExposure] = useState<ExposureResponse | null>(null);

  async function run(p: SignalParams) {
    setRunning(true);
    setError(null);
    setTopN(p.topN);
    const spec: SignalSpec = {
      name: "user_factor",
      hypothesis: "user-supplied factor",
      expression: p.expression,
      operators_used: p.operators_used,
      lookback: Math.max(p.lookback, 5),
      universe: "SP500",
      justification: "interactive signal run",
    };
    const [t1, t2, t3] = await Promise.all([
      signalToday(spec, p.topN, p.neutralize),
      signalIcTimeseries(spec, p.icLookback, p.neutralize),
      signalExposure(spec, p.topN, p.neutralize),
    ]);
    if (t1.error || t2.error || t3.error) {
      setError(t1.error ?? t2.error ?? t3.error);
    } else {
      setToday(t1.data);
      setIcTs(t2.data);
      setExposure(t3.data);
    }
    setRunning(false);
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-text">{t(locale, "signal.title")}</h1>
        <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
          {t(locale, "signal.subtitle")}
        </p>
      </header>

      <SignalForm running={running} onRun={run} />

      {error && (
        <Card padding="md">
          <p className="text-base text-red">{error}</p>
        </Card>
      )}

      {today && (
        <SignalSurvivorshipBadge
          corrected={today.survivorship_corrected ?? false}
          asOf={today.membership_as_of ?? null}
          neutralize={today.neutralize ?? "none"}
        />
      )}

      <TopBottomTable today={today} loading={running && !today} />
      <ICTimeseriesChart data={icTs} loading={running && !icTs} />
      <ExposureChart data={exposure} topN={topN} loading={running && !exposure} />
    </div>
  );
}

function SignalSurvivorshipBadge({
  corrected, asOf, neutralize,
}: {
  readonly corrected: boolean;
  readonly asOf: string | null;
  readonly neutralize: "none" | "sector";
}) {
  const { locale } = useLocale();
  return (
    <div className="flex flex-wrap gap-2">
      {corrected ? (
        <span className="inline-block rounded-md border border-green/40 bg-green/10 px-2 py-0.5 text-[11px] text-green">
          {t(locale, "backtest.kpi.survivorshipCorrected").replace("{date}", asOf ?? "—")}
        </span>
      ) : (
        <span className="inline-block rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-600 dark:text-amber-400">
          {t(locale, "backtest.kpi.survivorshipLegacy")}
        </span>
      )}
      {neutralize === "sector" && (
        <span className="inline-block rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
          ✓ {t(locale, "backtest.form.neutralize.sector")}
        </span>
      )}
    </div>
  );
}
