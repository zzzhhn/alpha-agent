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
      signalToday(spec, p.topN),
      signalIcTimeseries(spec, p.icLookback),
      signalExposure(spec, p.topN),
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

      <TopBottomTable today={today} loading={running && !today} />
      <ICTimeseriesChart data={icTs} loading={running && !icTs} />
      <ExposureChart data={exposure} topN={topN} loading={running && !exposure} />
    </div>
  );
}
