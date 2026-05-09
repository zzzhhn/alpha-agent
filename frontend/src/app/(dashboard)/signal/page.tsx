"use client";

/**
 * Signal page — workstation port (Stage 3 · 4/9).
 *
 * Layout: TmSubbar (universe + status pills + retry) → SIGNAL.FORM
 * pane (textarea + sliders + neutralize chips + factor examples) →
 * SIGNAL.TODAY pane (long basket / short basket via TmCols2) →
 * IC.TIMESERIES pane (4 KPIs + recharts) → EXPOSURE pane (sector +
 * cap quintile via TmCols2).
 *
 * All four child panes are workstation-aesthetic Tm* siblings so we
 * don't disturb the legacy `/report` page that still imports the
 * original `TopBottomTable` and `ExposureChart`. They co-exist until
 * the report page is ported (S3 · 8/9).
 *
 * Signal-spec construction, parallel fetch, and survivorship-badge
 * surfacing are byte-equivalent to the legacy page; only presentation
 * changed.
 */

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmScreen } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmPane } from "@/components/tm/TmPane";
import {
  TmSignalForm,
  type SignalParams,
} from "@/components/signal/TmSignalForm";
import { TmTopBottomTable } from "@/components/signal/TmTopBottomTable";
import { TmICTimeseriesChart } from "@/components/signal/TmICTimeseriesChart";
import { TmExposureChart } from "@/components/signal/TmExposureChart";
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

  // Surface the survivorship + neutralize state in the subbar so the
  // user always sees the methodology guard tags above the results.
  const survivorshipCorrected = today?.survivorship_corrected ?? false;
  const survivorshipAsOf = today?.membership_as_of ?? null;
  const neutralizeMode = today?.neutralize ?? "none";

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">SIGNAL</span>
        <TmSubbarSep />
        <TmSubbarKV label="UNIVERSE" value="SP500" />
        {today && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label="VALID"
              value={`${today.n_valid}/${today.universe_size}`}
            />
            <TmSubbarSep />
            <TmSubbarKV label="AS_OF" value={today.as_of} />
          </>
        )}
        <TmSubbarSpacer />
        {today && (
          <TmStatusPill tone={survivorshipCorrected ? "ok" : "warn"}>
            {survivorshipCorrected
              ? `SP500-AS-OF · ${survivorshipAsOf ?? "—"}`
              : "LEGACY (NO MEMBERSHIP MASK)"}
          </TmStatusPill>
        )}
        {neutralizeMode === "sector" && (
          <TmStatusPill tone="ok">SECTOR-NEUTRAL</TmStatusPill>
        )}
        {running && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        {error && <TmStatusPill tone="err">ERROR</TmStatusPill>}
      </TmSubbar>

      <TmSignalForm running={running} onRun={run} />

      {error && (
        <TmPane title="ERROR" meta="signal run failed">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      <TmTopBottomTable today={today} loading={running && !today} />
      <TmICTimeseriesChart data={icTs} loading={running && !icTs} />
      <TmExposureChart
        data={exposure}
        topN={topN}
        loading={running && !exposure}
      />

      {/* Footer hint when nothing has been run yet — keeps the screen
          from ending in raw bg-tm-bg if the user just landed. */}
      {!today && !icTs && !exposure && !running && (
        <TmPane title="USAGE" meta="hint">
          <p className="px-3 py-2 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
            {t(locale, "signal.subtitle")}
          </p>
        </TmPane>
      )}
    </TmScreen>
  );
}
