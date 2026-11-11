"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton, TmRowButton } from "@/components/tm/TmButton";
import { TmInput, TmNumberInput, TmTextarea } from "@/components/tm/TmField";
import { TmSelectMenu } from "@/components/tm/TmSelectMenu";
import { TmDialog } from "@/components/tm/TmDialog";
import { TmPagination } from "@/components/tm/TmPagination";
import { FACTOR_EXAMPLES, type FactorExample } from "@/components/alpha/FactorExamples";
import type { ZooEntry } from "@/lib/factor-zoo";
import styles from "./report-composer.module.css";
import { RESEARCH_NUMBER_LIMITS, researchNumberError } from "@/lib/research-input-validation";

export interface ReportConfig {
  readonly direction: "long_short" | "long_only" | "short_only";
  readonly neutralize: "none" | "sector";
  readonly benchmarkTicker: "SPY" | "RSP";
  readonly transactionCostBps: number;
}

export function isReportDraftDirty(name: string, expression: string, config: ReportConfig, report: { readonly name: string; readonly expression: string; readonly config: ReportConfig } | null): boolean {
  if (!report) return false;
  return (name.trim() || "user_factor") !== report.name || expression.trim() !== report.expression ||
    config.direction !== report.config.direction || config.neutralize !== report.config.neutralize ||
    config.benchmarkTicker !== report.config.benchmarkTicker || config.transactionCostBps !== report.config.transactionCostBps;
}

export function reportDirectionLabel(value: ReportConfig["direction"], locale: "zh" | "en") {
  const labels = {
    long_short: { zh: "多空", en: "Long / short" },
    long_only: { zh: "只做多", en: "Long only" },
    short_only: { zh: "只做空", en: "Short only" },
  };
  return labels[value][locale];
}

/** Search the entire source, then paginate. Fixture performance is never a live result. */
export function filterReportLibrary<T extends { readonly name: string; readonly expression: string }>(entries: readonly T[], query: string): readonly T[] {
  const term = query.trim().toLocaleLowerCase();
  return term ? entries.filter((entry) => `${entry.name} ${entry.expression}`.toLocaleLowerCase().includes(term)) : entries;
}

export function ReportComposer({
  factorName, onFactorName, expr, onExpr, config, onConfig, zoo,
  running, sourceName, onExample, onZoo, onGenerate,
}: {
  readonly factorName: string;
  readonly onFactorName: (value: string) => void;
  readonly expr: string;
  readonly onExpr: (value: string) => void;
  readonly config: ReportConfig;
  readonly onConfig: (fn: ReportConfig | ((current: ReportConfig) => ReportConfig)) => void;
  readonly zoo: readonly ZooEntry[];
  readonly running: boolean;
  readonly sourceName: string | null;
  readonly onExample: (example: FactorExample) => void;
  readonly onZoo: (entry: ZooEntry) => void;
  readonly onGenerate: () => void;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const costError = researchNumberError("transactionCostBps", config.transactionCostBps, locale);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [librarySource, setLibrarySource] = useState("examples");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const filteredExamples = filterReportLibrary(FACTOR_EXAMPLES, query);
  const filteredZoo = filterReportLibrary(zoo, query);
  const entries = librarySource === "examples" ? filteredExamples : filteredZoo;
  const pageCount = Math.max(1, Math.ceil(entries.length / 5));
  const currentPage = Math.min(page, pageCount);
  const visibleEntries = entries.slice((currentPage - 1) * 5, currentPage * 5);

  return (
    <TmPane title={zh ? "报告配置" : "Report setup"} meta={running ? (zh ? "正在生成报告" : "Generating report") : sourceName ? (zh ? "当前草稿 · 已载入" : "Current draft · loaded") : (zh ? "S&P 500 · 训练 / 测试 70 / 30（本页固定）" : "S&P 500 · train / test 70 / 30 (fixed on this page)")} className={`report-chrome ${styles.composer}`}>
      <div className="grid min-w-0 grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)]">
        <div className="min-w-0 p-4 lg:border-r lg:border-tm-rule">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="font-tm-mono text-xs text-tm-muted">{zh ? "研究因子" : "Research factor"}</span>
            <TmButton variant="secondary" onClick={() => setLibraryOpen(true)} disabled={running} aria-haspopup="dialog">
              {zh ? "从示例 / 因子库载入" : "Load example / saved factor"}
            </TmButton>
          </div>
          <div className="flex flex-col gap-3">
            <TmInput label={zh ? "名称" : "Name"} value={factorName} onChange={onFactorName} disabled={running} placeholder={zh ? "为这次研究命名" : "Name this research"} />
            <TmTextarea label={zh ? "表达式" : "Expression"} value={expr} onChange={onExpr} disabled={running} rows={2} spellCheck={false} placeholder="rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))" textareaClassName="min-h-[64px] resize-y leading-relaxed" />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-tm-rule pt-3">
              <p className="font-tm-mono text-xs text-tm-muted">{zh ? "运行后生成回测、风险与信号证据。" : "Run to generate backtest, risk and signal evidence."}</p>
              <TmButton variant="primary" size="md" onClick={onGenerate} disabled={!expr.trim() || running || Boolean(costError)} loading={running} loadingLabel={zh ? "正在生成报告" : "Generating report"}>
                {zh ? "生成报告" : "Generate report"}
              </TmButton>
            </div>
          </div>
        </div>
        <fieldset disabled={running} className="min-w-0 border-t border-tm-rule bg-tm-bg-2/40 p-4 lg:border-t-0">
          <legend className="sr-only">{zh ? "研究参数" : "Research parameters"}</legend>
          <div className="grid grid-cols-2 gap-x-4 gap-y-4">
            <ConfigSelect label={zh ? "交易方向" : "Direction"} value={config.direction} options={(["long_short", "long_only", "short_only"] as const).map((value) => ({ value, label: reportDirectionLabel(value, locale) }))} onChange={(direction) => onConfig((c) => ({ ...c, direction: direction as ReportConfig["direction"] }))} disabled={running} />
            <ConfigSelect label={zh ? "中性化" : "Neutralization"} value={config.neutralize} options={[{ value: "none", label: zh ? "不中性化" : "None" }, { value: "sector", label: zh ? "行业中性" : "Sector neutral" }]} onChange={(neutralize) => onConfig((c) => ({ ...c, neutralize: neutralize as ReportConfig["neutralize"] }))} disabled={running} />
            <ConfigSelect label={zh ? "比较基准" : "Benchmark"} value={config.benchmarkTicker} options={[{ value: "SPY", label: "SPY" }, { value: "RSP", label: "RSP" }]} onChange={(benchmarkTicker) => onConfig((c) => ({ ...c, benchmarkTicker: benchmarkTicker as ReportConfig["benchmarkTicker"] }))} disabled={running} />
            <TmNumberInput label={zh ? "交易成本（基点）" : "Trading cost (bps)"} {...RESEARCH_NUMBER_LIMITS.transactionCostBps} error={costError} step={1} value={config.transactionCostBps} onChange={(transactionCostBps) => onConfig((c) => ({ ...c, transactionCostBps }))} disabled={running} inputClassName="text-right" />
          </div>
          <div className="mt-4 border-t border-tm-rule pt-3 font-tm-mono text-xs leading-5 text-tm-muted">
            {zh ? "多头 / 空头各取 30% · 示例仅载入草稿，不自动计算。" : "Top / bottom 30% · loading a source does not run a backtest."}
          </div>
        </fieldset>
      </div>
      <TmDialog open={libraryOpen} onClose={() => setLibraryOpen(false)} title={zh ? "载入研究因子" : "Load a research factor"} closeLabel={zh ? "关闭因子选择" : "Close factor library"} className="!max-w-[850px]" bodyClassName="!p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-tm-rule p-4">
          <ConfigSelect label={zh ? "来源" : "Source"} value={librarySource} options={[{ value: "examples", label: zh ? `历史示例 · ${FACTOR_EXAMPLES.length}` : `Historical examples · ${FACTOR_EXAMPLES.length}` }, { value: "zoo", label: zh ? `因子库 · ${zoo.length}` : `Saved factors · ${zoo.length}` }]} onChange={(value) => { setLibrarySource(value); setPage(1); }} disabled={running} />
          <TmInput label={zh ? "搜索" : "Search"} value={query} onChange={(value) => { setQuery(value); setPage(1); }} placeholder={zh ? "名称或表达式" : "Name or expression"} className="min-w-[180px] flex-1" />
        </div>
        <p className="border-b border-tm-rule bg-tm-bg-2 px-4 py-2 font-tm-mono text-xs leading-5 text-tm-muted">
          {librarySource === "examples" ? (zh ? "历史示例来自 2026-05-08 验证记录，不代表当前收益或本次结果。选择后请核对参数，再生成报告。" : "Examples originate from the 2026-05-08 validation record, not current returns or this run. Review settings before generating.") : (zh ? "载入已保存的表达式与研究假设，沿用当前可见参数。" : "Load a saved expression and hypothesis with the currently visible settings.")}
        </p>
        <div className="min-h-[280px]" aria-live="polite">
          {visibleEntries.length ? visibleEntries.map((entry) => (
            <TmRowButton key={entry.expression + entry.name} disabled={running} className="border-b border-tm-rule px-4 py-3" onClick={() => {
              if (librarySource === "examples") onExample(entry as FactorExample);
              else onZoo(entry as ZooEntry);
              setLibraryOpen(false);
            }}>
              <span className="flex items-start justify-between gap-4 font-tm-mono text-xs"><span className="font-semibold text-tm-fg">{entry.name}</span><span className="shrink-0 text-tm-accent">{zh ? "载入草稿" : "Load draft"}</span></span>
              <code className="mt-1 block break-all font-tm-mono text-xs leading-5 text-tm-muted">{entry.expression}</code>
            </TmRowButton>
          )) : <p className="p-6 font-tm-mono text-xs text-tm-muted">{zh ? "没有匹配的因子。可修改搜索，或关闭后输入自定义表达式。" : "No matching factor. Change the search or close this window to enter a custom expression."}</p>}
        </div>
        <TmPagination page={currentPage} pageSize={5} totalItems={entries.length} pageSizeOptions={[5]} onPageChange={setPage} onPageSizeChange={() => {}} disabled={running} labels={{ navigation: zh ? "因子库分页" : "Factor library pagination", previous: zh ? "上一页" : "Previous", previousAriaLabel: zh ? "上一页因子" : "Previous factor page", next: zh ? "下一页" : "Next", nextAriaLabel: zh ? "下一页因子" : "Next factor page", page: (current, count) => `${current} / ${count}`, pageSize: zh ? "每页" : "Per page", total: (total) => zh ? `共 ${total} 个因子` : `${total} factors` }} />
      </TmDialog>
    </TmPane>
  );
}

function ConfigSelect({ label, value, options, onChange, disabled }: { readonly label: string; readonly value: string; readonly options: readonly { value: string; label: string }[]; readonly onChange: (value: string) => void; readonly disabled: boolean }) {
  return <div className="flex min-w-0 flex-col gap-1"><span className="font-tm-mono text-xs font-semibold text-tm-muted">{label}</span><TmSelectMenu value={value} options={options} onChange={onChange} ariaLabel={label} disabled={disabled} size="md" className="min-w-0" buttonClassName="w-full justify-between" /></div>;
}

export function ReportEvidenceEmpty({ running, failed, hasDraft }: { readonly running: boolean; readonly failed: boolean; readonly hasDraft: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <div className="grid min-w-0 grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)]" aria-busy={running || undefined}>
      <TmPane title={zh ? "研究报告" : "Research report"} meta={running ? (zh ? "证据计算中" : "Computing evidence") : (zh ? "尚无本次结果" : "No run results")} className="lg:border-r lg:border-tm-rule">
        <div className="px-5 py-6" role="status">
          <p className="font-tm-serif text-[18px] text-tm-fg">{running ? (zh ? "正在汇总研究证据" : "Assembling research evidence") : failed ? (zh ? "本次报告未生成" : "This report was not generated") : (zh ? "先定义因子，再判断证据" : "Define the factor. Then judge the evidence.")}</p>
          <p className="mt-2 max-w-xl text-sm leading-6 text-tm-muted">{running ? (zh ? "回测、当日信号、敞口与 IC 时间序列完成后，结论和净值曲线会显示在这里。" : "The verdict and equity curve appear here once the backtest, current signals, exposure and IC series return.") : failed ? (zh ? "草稿与参数仍保留在上方。查看错误后可再次生成，不会显示不完整的结论。" : "Your draft and settings are preserved above. Review the error and generate again; incomplete evidence is not a verdict.") : hasDraft ? (zh ? "草稿已准备好。核对右侧参数，点击「生成报告」开始计算。" : "The draft is ready. Review settings and select Generate report.") : (zh ? "输入表达式，或从历史示例与因子库载入。报告将保留样本外表现、风险和反证，不预设正面结论。" : "Enter an expression or load a source. The report retains out-of-sample performance, risks and counter-evidence without assuming a positive verdict.")}</p>
          <div className="mt-5 grid grid-cols-3 gap-3 border-t border-tm-rule pt-3 font-tm-mono text-xs text-tm-muted">{(zh ? ["样本外结论", "净值与回撤", "可打印研究报告"] : ["OOS verdict", "Equity & drawdown", "Printable report"]).map((label) => <span key={label}>{label}</span>)}</div>
        </div>
      </TmPane>
      <TmPane title={zh ? "证据检查" : "Evidence checks"}>
        <dl className="px-4 py-2 font-tm-mono text-xs">{(zh ? ["样本外回测", "Alpha 显著性与市场暴露", "当日信号与 IC", "风险和收益归因"] : ["Out-of-sample backtest", "Alpha significance & market beta", "Current signals & IC", "Risk and return attribution"]).map((label) => <div key={label} className="flex justify-between gap-3 border-b border-tm-rule py-3 last:border-0"><dt className="text-tm-fg-2">{label}</dt><dd className="shrink-0 text-tm-muted">{running ? (zh ? "计算中" : "Pending") : "—"}</dd></div>)}</dl>
      </TmPane>
    </div>
  );
}
