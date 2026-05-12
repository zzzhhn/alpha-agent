"use client";

import type { CronRun } from "@/lib/api/alerts";
import clsx from "clsx";

interface AlertListProps {
  readonly cronRuns: Record<string, CronRun[]>;
}

export default function AlertList({ cronRuns }: AlertListProps) {
  const entries = Object.entries(cronRuns);

  if (entries.length === 0) {
    return (
      <div className="px-3 py-6 font-tm-mono text-[11px] text-tm-muted">
        No cron jobs registered yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {entries.map(([name, runs]) => (
        <section key={name} className="border-b border-tm-rule last:border-b-0">
          <header className="flex items-center gap-3 bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10.5px]">
            <span className="font-semibold uppercase tracking-[0.06em] text-tm-fg-2">
              {name}
            </span>
            <span className="text-tm-muted">{runs.length} run{runs.length !== 1 ? "s" : ""}</span>
          </header>
          {runs.length === 0 ? (
            <div className="px-3 py-2 font-tm-mono text-[10.5px] text-tm-muted">
              No runs yet
            </div>
          ) : (
            <ul className="divide-y divide-tm-rule">
              {runs.map((r, i) => {
                const durationMs =
                  r.finished_at
                    ? new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()
                    : null;
                return (
                  <li
                    key={i}
                    className="flex items-center gap-3 px-3 py-1.5 font-tm-mono text-[10.5px]"
                  >
                    <span
                      className={clsx(
                        "font-semibold",
                        r.ok ? "text-tm-pos" : "text-tm-neg",
                      )}
                    >
                      {r.ok ? "OK" : "ERR"}
                    </span>
                    <span className="tabular-nums text-tm-fg-2">
                      {new Date(r.started_at).toLocaleString()}
                    </span>
                    {durationMs !== null ? (
                      <span className="text-tm-muted">
                        {(durationMs / 1000).toFixed(1)}s
                      </span>
                    ) : (
                      <span className="text-tm-warn">running…</span>
                    )}
                    {r.error_count > 0 ? (
                      <span className="text-tm-neg">
                        {r.error_count} error{r.error_count > 1 ? "s" : ""}
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
