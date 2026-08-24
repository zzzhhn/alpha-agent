"use client";

import { useState, type ReactNode } from "react";
import type { Locale } from "@/lib/i18n";
import { TmBadge, type TmBadgeTone } from "@/components/tm/TmBadge";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmPane } from "@/components/tm/TmPane";
import { TmStatePane, type TmState } from "@/components/tm/TmStatePane";
import { TmChip } from "@/components/tm/TmSubbar";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";

const SIGNALS = ["quality_momentum", "iv_term_residual", "cashflow_quality", "revision_breadth"] as const;
const ROW_STATES: ReadonlyArray<{ state: string; tone: TmBadgeTone }> = [
  { state: "PASS", tone: "positive" },
  { state: "REVIEW", tone: "warning" },
  { state: "BLOCKED", tone: "negative" },
  { state: "QUEUED", tone: "info" },
];
const DEMO_ROWS = Array.from({ length: 23 }, (_, index) => ({
  id: `A-${String(104 + index).padStart(3, "0")}`,
  signal: SIGNALS[index % SIGNALS.length],
  score: index % 7 === 2 ? "—" : `+${(1.84 - index * 0.04).toFixed(2)}σ`,
  ...ROW_STATES[index % ROW_STATES.length],
}));

const STATES: readonly TmState[] = ["loading", "empty", "error", "unauthorized", "stale", "partial"];

export function ReferenceDataFeedback({
  locale,
  mode,
}: {
  readonly locale: Locale;
  readonly mode: "data" | "feedback";
}) {
  return mode === "data" ? <DataSpecimens locale={locale} /> : <FeedbackSpecimens locale={locale} />;
}

function DataSpecimens({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const visibleRows = DEMO_ROWS.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div>
      <TmPane title="DATA.BADGE + KPI" bodyClassName="p-4">
        <div className="mb-4 flex flex-wrap gap-2">
          <TmBadge tone="neutral">NEUTRAL</TmBadge>
          <TmBadge tone="positive">VALIDATED</TmBadge>
          <TmBadge tone="warning">REVIEW</TmBadge>
          <TmBadge tone="negative">BLOCKED</TmBadge>
          <TmBadge tone="info">INFORMATION</TmBadge>
        </div>
        <TmKpiGrid>
          <TmKpi label={zh ? "样本数" : "Sample size"} value="1,248" sub="N · OOS" />
          <TmKpi label="SHARPE" value="1.84" sub="net of 10 bps" tone="pos" />
          <TmKpi label={zh ? "数据新鲜度" : "Freshness"} value="18m" sub="last verified" tone="warn" />
          <TmKpi label={zh ? "失败项" : "Failed gates"} value="1 / 5" sub="coverage" tone="neg" />
        </TmKpiGrid>
      </TmPane>

      <TmPane title="DATA.TABLE + PAGINATION" meta={zh ? "选择、排序与分页语义统一" : "shared selection, sorting, and paging grammar"}>
        <TmTableFrame>
          <TmTable caption={zh ? "信号评分示例" : "Signal score example"}>
            <TmTableHead>
              <TmTableRow>
                <TmTableHeaderCell>ID</TmTableHeaderCell>
                <TmTableHeaderCell>{zh ? "信号" : "Signal"}</TmTableHeaderCell>
                <TmTableHeaderCell textAlign="right" sortDirection="descending">{zh ? "评分" : "Score"}</TmTableHeaderCell>
                <TmTableHeaderCell textAlign="right">{zh ? "状态" : "Status"}</TmTableHeaderCell>
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {visibleRows.map((row) => (
                <TmTableRow
                  key={row.id}
                  selected={row.id === "A-104"}
                >
                  <TmTableRowHeader>{row.id}</TmTableRowHeader>
                  <TmTableCell>{row.signal}</TmTableCell>
                  <TmTableCell textAlign="right" numeric>{row.score}</TmTableCell>
                  <TmTableCell textAlign="right">
                    <TmBadge tone={row.tone}>{row.state}</TmBadge>
                  </TmTableCell>
                </TmTableRow>
              ))}
            </TmTableBody>
          </TmTable>
        </TmTableFrame>
        <TmPagination
          page={page}
          pageSize={pageSize}
          totalItems={DEMO_ROWS.length}
          pageSizeOptions={[5, 10, 20]}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          labels={{
            navigation: zh ? "示例表格分页" : "Sample table pagination",
            previous: zh ? "上一页" : "Previous",
            previousAriaLabel: zh ? "上一页" : "Previous page",
            next: zh ? "下一页" : "Next",
            nextAriaLabel: zh ? "下一页" : "Next page",
            page: (current, count) => zh ? `第 ${current} / ${count} 页` : `Page ${current} / ${count}`,
            pageSize: zh ? "每页" : "Rows",
            total: (total) => zh ? `共 ${total} 条` : `${total} total`,
          }}
        />
      </TmPane>
    </div>
  );
}

function FeedbackSpecimens({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const [state, setState] = useState<TmState>("empty");
  const copy: Record<TmState, { title: string; description: ReactNode }> = {
    loading: { title: zh ? "正在加载证据" : "Loading evidence", description: zh ? "保持面板尺寸并说明当前阶段。" : "Keep the pane geometry and narrate the current stage." },
    empty: { title: zh ? "尚无运行结果" : "No run results yet", description: zh ? "运行一次分析后，这里会显示可验证证据。" : "Run an analysis to populate this pane with verifiable evidence." },
    error: { title: zh ? "证据加载失败" : "Evidence failed to load", description: zh ? "只重试受影响的面板，其他上下文保持可用。" : "Retry only the affected pane and preserve the rest of the context." },
    unauthorized: { title: zh ? "需要登录" : "Sign-in required", description: zh ? "登录后恢复到当前研究上下文。" : "Return to the current research context after sign-in." },
    stale: {
      title: zh ? "数据已过期" : "Data is stale",
      description: zh
        ? "示例：最后验证于 2026-08-24 08:32 UTC。刷新前暂停生成新决策。"
        : "Sample: last verified at 2026-08-24 08:32 UTC. New decisions pause until refresh.",
    },
    partial: {
      title: zh ? "部分证据可用" : "Partial evidence available",
      description: zh
        ? "示例：5 项证据中已完成 4 项；官方 self-correlation 暂不可用。仅重试缺失项。"
        : "Sample: 4 of 5 evidence checks completed; official self-correlation is unavailable. Retry only the missing check.",
    },
  };
  return (
    <TmPane title="FEEDBACK.STATE PANE" meta={zh ? "稳定几何 + 局部恢复" : "stable geometry + local recovery"} bodyClassName="p-4">
      <div className="mb-4 flex flex-wrap gap-1.5">
        {STATES.map((value) => (
          <TmChip key={value} on={state === value} onClick={() => setState(value)}>
            {value.toUpperCase()}
          </TmChip>
        ))}
      </div>
      <TmStatePane
        state={state}
        title={copy[state].title}
        description={copy[state].description}
        action={state === "loading" ? undefined : {
          label: state === "unauthorized" ? (zh ? "前往登录" : "Sign in") : (zh ? "重试此面板" : "Retry this pane"),
          onClick: () => setState("loading"),
          variant: state === "unauthorized" ? "primary" : "secondary",
        }}
      />
    </TmPane>
  );
}
