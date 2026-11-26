"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiException, apiGet, apiPost } from "@/lib/api/client";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";
import { TmPagination } from "@/components/tm/TmPagination";

interface ChangeRow {
  id: number;
  field: string;
  old_value: string | null;
  new_value: string | null;
  changed_at: string;
  source: string;
  rollback_of: number | null;
  rollback_status?: string;
  provider?: string | null;
  old_provider?: string | null;
}

const PAGE_SIZE = 5;
const ROLLBACK_STATUS_LABELS: Record<string, readonly [string, string]> = {
  unverified: ["历史记录缺少可核实的凭据关联", "Credential link could not be verified"],
  different_provider: ["服务商与当前凭据不一致", "Provider does not match the current credential"],
  stale_revision: ["凭据版本已更新", "Credential revision has changed"],
  value_changed: ["当前值已变化", "Current value has changed"],
  already_rolled_back: ["已回滚", "Already rolled back"],
};

export function changeRollbackLabel(status: string | undefined, zh: boolean): string | null {
  return ROLLBACK_STATUS_LABELS[status ?? ""]?.[zh ? 0 : 1] ?? null;
}

const FIELD_LABELS: Record<string, readonly [string, string]> = {
  "byok.provider": ["模型服务商", "Model provider"],
  "byok.model": ["模型", "Model"],
  "byok.base_url": ["模型 API 地址", "Model endpoint"],
  "byok.api_key": ["模型密钥（不显示内容）", "Model key (value hidden)"],
  "factor.custom_expression": ["线上因子表达式", "Live factor expression"],
  "factor.mode": ["因子模式", "Factor mode"],
  "signal_weights": ["信号权重", "Signal weights"],
};

/** Readable label for a config field; unknown fields fall back to the raw key. */
export function changeFieldLabel(field: string, zh: boolean): string {
  const label = FIELD_LABELS[field];
  return label ? label[zh ? 0 : 1] : field;
}

function relTime(iso: string, locale: "zh" | "en"): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return locale === "zh" ? "刚刚" : "just now";
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

export default function ChangeLog({
  onApplied,
  onConflict,
  disabled = false,
  onBusyChange,
  revision,
}: {
  readonly onApplied?: () => void;
  readonly onConflict?: () => void;
  readonly disabled?: boolean;
  readonly onBusyChange?: (busy: boolean) => void;
  readonly revision?: string | null;
} = {}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const emptyValue = zh ? "（空）" : "(empty)";
  const [rows, setRows] = useState<ChangeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<ChangeRow | null>(null);
  const [rolling, setRolling] = useState(false);
  const [rollbackError, setRollbackError] = useState("");
  const [applied, setApplied] = useState(false);
  const rollbackLock = useRef(false);
  const readGeneration = useRef(0);

  const load = useCallback(async () => {
    const generation = ++readGeneration.current;
    setLoading(true);
    setErr("");
    try {
      const r = await apiGet<{ changes: ChangeRow[] }>(
        "/api/user/settings/history?limit=50",
      );
      if (generation !== readGeneration.current) return;
      setRows(r.changes);
      setPage((current) => Math.min(current, Math.max(1, Math.ceil(r.changes.length / PAGE_SIZE))));
    } catch (e) {
      if (generation !== readGeneration.current) return;
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === readGeneration.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { ++readGeneration.current; };
  }, [load, revision]);

  const canRollbackPending = !loading && !err && rows.some(
    row => row.id === pending?.id && row.rollback_status === "available",
  );

  async function onRollback() {
    if (disabled || rollbackLock.current || !pending || !canRollbackPending) return;
    rollbackLock.current = true;
    setRolling(true);
    setRollbackError("");
    try {
      onBusyChange?.(true);
      const result = await apiPost<{ ok: boolean }, Record<string, never>>(
        `/api/user/settings/rollback/${pending.id}`, {},
      );
      if (!result.ok) throw new Error(zh ? "服务器未确认回滚。" : "The server did not confirm the rollback.");
    } catch (e) {
      if (e instanceof ApiException && e.status === 409) {
        setRollbackError(zh ? "当前配置已变化，无法回滚这条记录。" : "The current configuration changed. This entry cannot be rolled back.");
        void load();
        onConflict?.();
      } else {
        setRollbackError(e instanceof Error ? e.message : String(e));
      }
      return;
    } finally {
      rollbackLock.current = false;
      setRolling(false);
      onBusyChange?.(false);
    }
    setPending(null);
    setApplied(true);
    void load();
    onApplied?.();
  }

  function closeDialog() {
    if (rollbackLock.current) return;
    setPending(null);
    setRollbackError("");
  }

  const visible = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const previous = zh ? "上一页" : "Previous";
  const next = zh ? "下一页" : "Next";

  return (
    <>
      {applied ? <p role="status" className="border-b border-tm-rule px-3 py-2 text-xs text-tm-pos">
        {zh ? "已回滚设置。" : "Setting rolled back."}
      </p> : null}
      {err ? <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2 text-xs">
        <p role="alert" className="min-w-0 text-tm-neg [overflow-wrap:anywhere]">
          {zh ? "无法刷新变更记录：" : "Could not refresh change history: "}{err}
        </p>
        <TmButton variant="secondary" size="xs" disabled={loading} onClick={() => void load()}>
          {zh ? "重试" : "Retry"}
        </TmButton>
      </div> : null}
      {rows.length === 0 && !err ? <p role="status" className="px-3 py-3 text-xs text-tm-muted">
        {loading ? (zh ? "正在读取变更记录…" : "Loading change history…")
          : (zh ? "暂无设置变更记录" : "No setting changes yet")}
      </p> : null}
      {visible.length ? <ul role="list" className="divide-y divide-tm-rule" aria-busy={loading || undefined}>
        {visible.map((r) => (
          <li key={r.id} className="flex min-w-0 items-start gap-3 px-3 py-2 text-xs">
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-tm-fg [overflow-wrap:anywhere]" title={r.field}>{changeFieldLabel(r.field, zh)}</span>
                <time dateTime={r.changed_at} className="text-tm-muted">{relTime(r.changed_at, locale)}</time>
                {r.provider ? <span className="text-tm-muted">{r.old_provider && r.old_provider !== r.provider ? `${r.old_provider} → ` : ""}{r.provider}</span> : null}
                {r.source === "rollback" ? <span className="bg-tm-warn/20 px-1.5 text-tm-warn">
                  {zh ? "回滚" : "Rollback"}{r.rollback_of !== null ? ` #${r.rollback_of}` : ""}
                </span> : null}
              </div>
              <p className="font-tm-mono leading-5 [overflow-wrap:anywhere]">
                <span className="sr-only">{zh ? "旧值：" : "Previous value: "}</span>
                <span className="text-tm-muted line-through">{r.old_value ?? emptyValue}</span>
                <span aria-hidden="true" className="mx-2 text-tm-fg-2">→</span>
                <span className="sr-only">{zh ? "新值：" : "New value: "}</span>
                <span className="text-tm-fg">{r.new_value ?? emptyValue}</span>
              </p>
              {changeRollbackLabel(r.rollback_status, zh) ? <p className="text-tm-muted">{changeRollbackLabel(r.rollback_status, zh)}</p> : null}
            </div>
            {r.rollback_status === "available" ? <TmButton
              variant="secondary" size="xs" aria-haspopup="dialog" aria-disabled={disabled || loading || !!err}
              aria-label={zh ? `回滚 ${r.field}，变更 #${r.id}` : `Roll back ${r.field}, change #${r.id}`}
              onClick={() => {
                if (disabled || loading || err) return;
                setApplied(false);
                setPending(r);
              }}>
              {zh ? "回滚" : "Roll back"}
            </TmButton> : null}
          </li>
        ))}
      </ul> : null}
      {rows.length > 0 ? <TmPagination page={page} pageSize={PAGE_SIZE} pageSizeOptions={[PAGE_SIZE]}
        totalItems={rows.length} onPageChange={setPage} onPageSizeChange={() => {}} loading={loading}
        labels={{ navigation: zh ? "变更记录分页" : "Change history pagination",
          previous, previousAriaLabel: previous, next, nextAriaLabel: next, page: (current, total) => `${current} / ${total}`,
          pageSize: "", total: (count) => zh ? `已加载最近 ${count} 条` : `${count} recent changes loaded` }} /> : null}
      <TmDialog open={pending !== null} onClose={closeDialog} closeLabel={zh ? "关闭" : "Close"}
        title={zh ? "确认回滚设置？" : "Roll back this setting?"} className="max-w-lg">
        {pending ? <div className="space-y-3 text-sm text-tm-fg-2">
          <p>{zh ? "这会覆盖当前已保存的设置，并新增一条变更记录。API 密钥不会更改。"
            : "This replaces the current saved setting and adds a history entry. Your API key is unchanged."}</p>
          <p className="border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-xs [overflow-wrap:anywhere]">
            {pending.field} → {pending.old_value ?? emptyValue}
          </p>
          {rollbackError ? <p role="alert" className="text-tm-neg [overflow-wrap:anywhere]">{rollbackError}</p> : null}
          <div className="flex justify-end gap-2">
            <TmButton variant="secondary" onClick={closeDialog} disabled={rolling}>{zh ? "取消" : "Cancel"}</TmButton>
            <TmButton variant="danger" onClick={() => void onRollback()} loading={rolling} disabled={disabled || !canRollbackPending}
              loadingLabel={zh ? "回滚中…" : "Rolling back…"}>{zh ? "确认回滚" : "Confirm rollback"}</TmButton>
          </div>
        </div> : null}
      </TmDialog>
    </>
  );
}
