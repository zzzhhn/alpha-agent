"use client";

import { useMemo, useRef, useState, type ReactNode } from "react";
import { TmButton, TmRowButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";
import { TmInput, TmSelect } from "@/components/tm/TmField";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmPane } from "@/components/tm/TmPane";
import { TmTooltip } from "@/components/tm/TmTooltip";
import {
  TmTable, TmTableBody, TmTableCell, TmTableFrame, TmTableHead,
  TmTableHeaderCell, TmTableRow, TmTableRowHeader,
} from "@/components/tm/TmTable";
import { readDirection, type ZooEntry } from "@/lib/factor-zoo";
import { t } from "@/lib/i18n";
import { GlossaryTip } from "./GlossaryTip";
import {
  filterZooCatalog, isFiniteZooMetric,
  type ZooDirectionFilter, type ZooSortColumn, type ZooSortDirection, type ZooStatusFilter,
} from "./zoo-catalog";

export function ZooCatalog({
  entries, staleIds, locale, onLoadBacktest, onLoadReport, onLoadScreener, onDelete,
}: {
  readonly entries: readonly ZooEntry[] | null;
  readonly staleIds: ReadonlySet<string>;
  readonly locale: "zh" | "en";
  readonly onLoadBacktest: (entry: ZooEntry) => void;
  readonly onLoadReport: (entry: ZooEntry) => void;
  readonly onLoadScreener: (entry: ZooEntry) => void;
  readonly onDelete: (id: string) => boolean;
}) {
  const zh = locale === "zh";
  const catalog = zh ? "因子目录" : "Factor catalog";
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState<ZooDirectionFilter>("all");
  const [status, setStatus] = useState<ZooStatusFilter>("all");
  const [sort, setSort] = useState<ZooSortColumn>("savedAt");
  const [order, setOrder] = useState<ZooSortDirection>("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [detail, setDetail] = useState<ZooEntry | null>(null);
  const [deleting, setDeleting] = useState<ZooEntry | null>(null);
  const [deleteError, setDeleteError] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => filterZooCatalog(entries ?? [], {
    search, direction, status, staleIds, sort, order, locale,
  }), [entries, search, direction, status, staleIds, sort, order, locale]);
  const currentPage = Math.min(page, Math.max(1, Math.ceil(filtered.length / pageSize)));
  const start = (currentPage - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  const directions = {
    long_short: zh ? "多空" : "Long/short",
    long_only: zh ? "仅多头" : "Long only",
    short_only: zh ? "仅空头" : "Short only",
  };
  const actions = [
    { key: "zoo.actLoadBacktest", action: onLoadBacktest },
    { key: "zoo.actLoadReport", action: onLoadReport },
    { key: "zoo.actLoadScreener", action: onLoadScreener },
  ] as const;
  const close = zh ? "关闭" : "Close";

  function resetFilters() {
    setSearch("");
    setDirection("all");
    setStatus("all");
    setPage(1);
    searchRef.current?.focus();
  }

  function sortHeader(column: ZooSortColumn, label: string, numeric = false, tip?: ReactNode) {
    return (
      <TmTableHeaderCell
        className="whitespace-nowrap py-0"
        textAlign={numeric ? "right" : "left"}
        sortDirection={sort === column ? (order === "asc" ? "ascending" : "descending") : undefined}
      >
        <span className={`flex items-center gap-1 ${numeric ? "justify-end" : ""}`}>
          <TmRowButton
            className={`!w-auto py-2 ${sort === column ? "text-tm-accent" : ""}`}
            onClick={() => {
              setOrder(sort === column ? (order === "asc" ? "desc" : "asc") : column === "name" ? "asc" : "desc");
              setSort(column);
              setPage(1);
            }}
          >
            {label}<span aria-hidden="true" className="ml-1">{sort === column ? (order === "asc" ? "↑" : "↓") : "↕"}</span>
          </TmRowButton>
          {tip}
        </span>
      </TmTableHeaderCell>
    );
  }

  function metricCell(value: unknown, format: (n: number) => string) {
    return (
      <TmTableCell numeric textAlign="right" className="whitespace-nowrap">
        {isFiniteZooMetric(value) ? (
          <span className={value > 0 ? "text-tm-pos" : value < 0 ? "text-tm-neg" : ""}>{format(value)}</span>
        ) : <span aria-label={zh ? "未记录" : "Not recorded"} className="text-tm-muted">—</span>}
      </TmTableCell>
    );
  }

  function confirmDelete() {
    if (!deleting) return;
    if (!onDelete(deleting.id)) {
      setDeleteError(true);
      return;
    }
    // The triggering row will disappear; focus the persistent catalog search.
    setDeleting(null);
    searchRef.current?.focus();
  }

  return (
    <TmPane bodyClassName="min-w-0">
      <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
        <TmInput
          ref={searchRef}
          type="search"
          aria-label={zh ? "搜索名称或表达式" : "Search name or expression"}
          placeholder={zh ? "搜索名称或表达式" : "Search name or expression"}
          value={search}
          onChange={(value) => { setSearch(value); setPage(1); }}
          className="w-full sm:w-64"
        />
        <TmSelect
          aria-label={zh ? "方向" : "Direction"}
          value={direction}
          onChange={(value) => { setDirection(value as ZooDirectionFilter); setPage(1); }}
          options={[
            { value: "all", label: zh ? "全部方向" : "All directions" },
            ...Object.entries(directions).map(([value, label]) => ({ value, label })),
          ]}
        />
        <TmSelect
          aria-label={zh ? "状态" : "Status"}
          value={status}
          onChange={(value) => { setStatus(value as ZooStatusFilter); setPage(1); }}
          options={[
            { value: "all", label: zh ? "全部状态" : "All statuses" },
            { value: "champion", label: zh ? "测试夏普 ≥ 1" : "Test Sharpe ≥ 1" },
            { value: "stale", label: zh ? "待复测" : "Review due" },
          ]}
        />
        {(search || direction !== "all" || status !== "all") && (
          <TmButton variant="ghost" onClick={resetFilters}>{zh ? "清除筛选" : "Clear filters"}</TmButton>
        )}
      </div>
      {!entries ? (
        <p role="status" className="px-3 py-6 text-xs text-tm-muted">{zh ? "正在读取本地因子…" : "Reading local factors…"}</p>
      ) : visible.length === 0 ? (
        <p role="status" className="px-3 py-6 text-xs text-tm-muted">
          {entries.length === 0
            ? (zh ? "因子库为空。可从因子研究或回测页面保存因子。" : "No factors saved. Save one from Factor Research or Backtest.")
            : (zh ? "没有匹配的因子。请调整搜索或清除筛选。" : "No matching factors. Try a different search or clear the filters.")}
        </p>
      ) : (
        <TmTableFrame tabIndex={0} role="region" aria-label={catalog}>
          <TmTable density="standard" caption={catalog} className="min-w-[1240px] table-fixed">
            <colgroup>
              <col className="w-[184px]" /><col className="w-24" /><col />
              <col className="w-36" /><col className="w-28" /><col className="w-20" />
              <col className="w-32" /><col className={zh ? "w-[256px]" : "w-[400px]"} />
            </colgroup>
            <TmTableHead>
              <TmTableRow>
                {sortHeader("name", t(locale, "zoo.colName"))}
                <TmTableHeaderCell>{zh ? "方向" : "Direction"}</TmTableHeaderCell>
                <TmTableHeaderCell>{t(locale, "zoo.colExpr")}</TmTableHeaderCell>
                {sortHeader("sharpe", zh ? "测试夏普" : "Test Sharpe", true, <GlossaryTip term="SHARPE">?</GlossaryTip>)}
                {sortHeader("return", t(locale, "zoo.colReturn"), true)}
                {sortHeader("ic", t(locale, "zoo.colIc"), true, <GlossaryTip term="IC">?</GlossaryTip>)}
                {sortHeader("savedAt", t(locale, "zoo.colSavedAt"))}
                <TmTableHeaderCell textAlign="right">{zh ? "操作" : "Actions"}</TmTableHeaderCell>
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {visible.map((entry) => (
                <TmTableRow key={entry.id}>
                  <TmTableRowHeader className="py-2">
                    <TmRowButton aria-haspopup="dialog" onClick={() => setDetail(entry)} className="text-tm-accent">
                      <span className="line-clamp-2 break-words">{entry.name}</span>
                    </TmRowButton>
                    <div className="flex flex-wrap gap-x-2 text-xs font-normal text-tm-muted">
                      <span>{entry.curated ? (zh ? "内置示例" : "Curated example") : (zh ? "本地保存" : "Locally saved")}</span>
                      {staleIds.has(entry.id) && <span className="text-tm-warn">{zh ? "待复测" : "Review due"}</span>}
                    </div>
                  </TmTableRowHeader>
                  <TmTableCell>
                    {entry.direction ? directions[readDirection(entry)] : (
                      <TmTooltip content={zh ? "旧记录未保存方向，按默认多空显示。" : "This legacy entry did not record its direction; long/short is the default."}>
                        <span className="cursor-help border-b border-dotted border-tm-muted">{directions.long_short}</span>
                      </TmTooltip>
                    )}
                  </TmTableCell>
                  <TmTableCell><code className="line-clamp-2 break-all">{entry.expression}</code></TmTableCell>
                  {metricCell(entry.headlineMetrics?.testSharpe, (v) => v.toFixed(2))}
                  {metricCell(entry.headlineMetrics?.totalReturn, (v) => `${(v * 100).toFixed(1)}%`)}
                  {metricCell(entry.headlineMetrics?.testIc, (v) => v.toFixed(3))}
                  <TmTableCell className="whitespace-nowrap text-tm-muted">
                    {entry.curated
                      ? (zh ? "内置示例" : "Curated")
                      : Number.isFinite(Date.parse(entry.savedAt))
                        ? <time dateTime={entry.savedAt}>{new Date(entry.savedAt).toLocaleDateString(zh ? "zh-CN" : "en-CA")}</time>
                        : "—"}
                  </TmTableCell>
                  <TmTableCell textAlign="right">
                    <div className="flex justify-end gap-0.5">
                      {actions.map(({ key, action }) => (
                        <TmButton key={key} variant="ghost" size="xs" className="!px-1.5 !tracking-normal" aria-label={`${t(locale, key)}: ${entry.name}`} onClick={() => action(entry)}>
                          {t(locale, key)}
                        </TmButton>
                      ))}
                      <TmButton
                        variant="ghost" size="xs" className="!px-1.5 !tracking-normal" aria-haspopup="dialog" aria-label={`${t(locale, "zoo.actDelete")}: ${entry.name}`}
                        onClick={() => { setDeleteError(false); setDeleting(entry); }}
                      >
                        {t(locale, "zoo.actDelete")}
                      </TmButton>
                    </div>
                  </TmTableCell>
                </TmTableRow>
              ))}
            </TmTableBody>
          </TmTable>
        </TmTableFrame>
      )}
      {entries && filtered.length > 0 && (
        <TmPagination
          page={page} pageSize={pageSize} totalItems={filtered.length} pageSizeOptions={[5, 10]}
          onPageChange={setPage} onPageSizeChange={setPageSize}
          labels={{
            navigation: zh ? "因子目录分页" : "Factor catalog pagination",
            previous: zh ? "上一页" : "Prev", previousAriaLabel: zh ? "上一页" : "Previous page",
            next: zh ? "下一页" : "Next", nextAriaLabel: zh ? "下一页" : "Next page",
            page: (current, total) => `${current} / ${total}`,
            pageSize: zh ? "每页" : "Rows",
            total: (count) => zh
              ? `${start + 1}–${start + visible.length} / ${count} 个匹配因子`
              : `${start + 1}–${start + visible.length} of ${count} matching factors`,
          }}
        />
      )}
      <TmDialog open={detail !== null} onClose={() => setDetail(null)} title={detail?.name} closeLabel={close} className="!max-w-xl">
        {detail && (
          <div className="space-y-3 text-xs text-tm-fg-2">
            <div>
              <div className="mb-1 font-semibold">{t(locale, "zoo.colExpr")}</div>
              <code className="block break-all border border-tm-rule bg-tm-bg-2 p-3">{detail.expression}</code>
            </div>
            {detail.hypothesis && <p className="break-words">{detail.hypothesis}</p>}
            <p className="text-tm-muted">{detail.curated
              ? (zh ? "指标来自内置历史示例，不是当前回测。" : "Metrics are from the curated historical example, not a current backtest.")
              : (zh ? "指标为保存时的快照，不是当前回测。" : "Metrics are a saved snapshot, not a current backtest.")}</p>
            <div className="flex flex-wrap gap-2 border-t border-tm-rule pt-3">
              {actions.map(({ key, action }) => (
                <TmButton key={key} variant="secondary" onClick={() => { setDetail(null); action(detail); }}>
                  {t(locale, key)}
                </TmButton>
              ))}
            </div>
          </div>
        )}
      </TmDialog>
      <TmDialog
        open={deleting !== null} onClose={() => setDeleting(null)} closeLabel={close}
        title={zh ? "删除本地因子" : "Delete local factor"} className="!max-w-md"
      >
        <p className="break-words text-xs leading-5 text-tm-fg-2">
          {zh ? `删除「${deleting?.name}」？此操作仅影响当前浏览器，无法撤销。` : `Delete “${deleting?.name}”? This only affects this browser and cannot be undone.`}
        </p>
        {deleteError && <p role="alert" className="mt-2 text-xs text-tm-neg">{zh ? "未能写入本地存储，因子仍在目录中。" : "Local storage could not be updated. The factor is still in the catalog."}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <TmButton variant="secondary" onClick={() => setDeleting(null)}>{zh ? "取消" : "Cancel"}</TmButton>
          <TmButton variant="danger" onClick={confirmDelete}>{t(locale, "zoo.actDelete")}</TmButton>
        </div>
      </TmDialog>
    </TmPane>
  );
}
