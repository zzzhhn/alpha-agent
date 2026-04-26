"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { listZoo, removeFromZoo, type ZooEntry } from "@/lib/factor-zoo";

export default function FactorsPage() {
  const { locale } = useLocale();
  const router = useRouter();
  const [entries, setEntries] = useState<readonly ZooEntry[]>([]);

  function refresh() {
    setEntries(listZoo());
  }

  useEffect(() => {
    refresh();
  }, []);

  function loadIntoBacktest(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.backtest.prefill.v1",
        JSON.stringify({
          name: e.name,
          expression: e.expression,
          operators_used: extractOps(e.expression),
          lookback: 12,
          hypothesis: e.hypothesis,
        }),
      );
    } catch {
      /* ignore */
    }
    router.push("/backtest");
  }

  function loadIntoReport(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.report.prefill.v1",
        JSON.stringify(e),
      );
    } catch {
      /* ignore */
    }
    router.push("/report");
  }

  function deleteEntry(id: string) {
    removeFromZoo(id);
    refresh();
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-text">
          {t(locale, "zoo.title")}
        </h1>
        <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
          {t(locale, "zoo.subtitle")}
        </p>
      </header>

      <Card padding="md">
        {entries.length === 0 ? (
          <p className="py-6 text-center text-[14px] text-muted">
            {t(locale, "zoo.empty")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="bg-[var(--toggle-bg)]">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "zoo.colName")}</th>
                  <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "zoo.colExpr")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "zoo.colSharpe")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "zoo.colReturn")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "zoo.colIc")}</th>
                  <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "zoo.colSavedAt")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted"></th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-t border-border">
                    <td className="px-2 py-1.5 font-mono text-text">{e.name}</td>
                    <td className="px-2 py-1.5 max-w-[400px] truncate font-mono text-muted" title={e.expression}>
                      {e.expression}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">
                      {e.headlineMetrics?.testSharpe != null
                        ? renderColored(e.headlineMetrics.testSharpe.toFixed(2), e.headlineMetrics.testSharpe)
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">
                      {e.headlineMetrics?.totalReturn != null
                        ? renderColored(`${(e.headlineMetrics.totalReturn * 100).toFixed(1)}%`, e.headlineMetrics.totalReturn)
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">
                      {e.headlineMetrics?.testIc != null
                        ? renderColored(e.headlineMetrics.testIc.toFixed(3), e.headlineMetrics.testIc)
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-muted">
                      {new Date(e.savedAt).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => loadIntoBacktest(e)}>
                          {t(locale, "zoo.actLoadBacktest")}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => loadIntoReport(e)}>
                          {t(locale, "zoo.actLoadReport")}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => deleteEntry(e.id)}>
                          {t(locale, "zoo.actDelete")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function renderColored(label: string, value: number) {
  const cls = value > 0 ? "text-green" : value < 0 ? "text-red" : "text-text";
  return <span className={cls}>{label}</span>;
}

function extractOps(expr: string): string[] {
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
  const set = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(expr))) set.add(m[1]);
  return Array.from(set);
}
