"use client";

import { useEffect, useRef, useState } from "react";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmStatePane } from "@/components/tm/TmStatePane";
import type { ApiResponse } from "@/lib/types";
import type { Locale } from "@/lib/i18n";

type Result<T> = Pick<ApiResponse<T>, "data" | "error">;
type Snapshot<T> = Result<T> & { key: string; version: number; retry: number };

// Ignore superseded results without aborting shared API-cache promises.
export function useDataRequest<T>(
  key: string | null,
  version: number,
  load: (key: string, force: boolean) => Promise<Result<T>>,
) {
  const [snapshot, setSnapshot] = useState<Snapshot<T> | null>(null);
  const [retry, setRetry] = useState(0);
  const lastRetry = useRef(0);
  useEffect(() => {
    if (key === null) return;
    let current = true;
    const settle = (result: Result<T>) => {
      if (!current) return;
      setSnapshot((previous) => ({
        key, version, retry,
        data: result.data ?? (previous?.key === key ? previous.data : null),
        error: result.error,
      }));
    };
    // Global refresh invalidates the cache before changing version. Local
    // retry needs to bypass the cache once, for this request only.
    const force = retry !== lastRetry.current;
    lastRetry.current = retry;
    void load(key, force)
      .then((result) => settle(result.error || result.data !== null ? result : { data: null, error: "" }))
      .catch((error: unknown) => settle({ data: null, error: error instanceof Error ? error.message : "" }));
    return () => { current = false; };
  }, [key, version, retry, load]);

  const sameKey = key !== null && snapshot?.key === key ? snapshot : null;
  const pending = key !== null && (!sameKey || sameKey.version !== version || sameKey.retry !== retry);
  return {
    data: sameKey?.data ?? null,
    error: pending ? null : sameKey?.error ?? null,
    pending,
    retry: () => setRetry((previous) => previous + 1),
  };
}

export function DataRequestState({ locale, label, request }: {
  locale: Locale;
  label: string;
  request: { data: unknown; pending: boolean; error: string | null; retry: () => void };
}) {
  const zh = locale === "zh";
  if (request.pending && request.data) {
    return <p role="status" className="border-b border-tm-rule px-3 py-2 text-xs text-tm-muted">{zh ? "正在更新，暂显示上次结果。" : "Updating; showing the previous result."}</p>;
  }
  if (request.pending) return <TmStatePane state="loading" className="!min-h-24 !border-0 !py-4" title={zh ? `正在读取${label}…` : `Loading ${label}…`} />;
  if (request.error === null) return null;
  return (
    <TmStatePane
      state={request.data ? "stale" : "error"}
      className="!min-h-24 border-x-0 border-t-0 !py-4"
      title={zh ? `${label}读取失败` : `Could not load ${label}`}
      description={request.data ? (zh ? "仍显示上次读取的结果。" : "Still showing the previous result.") : undefined}
      action={{ label: zh ? "重试" : "Retry", onClick: request.retry }}
    />
  );
}

export function DataPagination({ locale, scope, page, pageSize, total, onChange }: {
  locale: Locale;
  scope: string;
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const zh = locale === "zh";
  return <TmPagination
    page={page}
    pageSize={pageSize}
    totalItems={total}
    pageSizeOptions={[pageSize]}
    onPageChange={onChange}
    onPageSizeChange={() => {}}
    labels={{
      navigation: zh ? `${scope}分页` : `${scope} pagination`,
      previous: zh ? "上一页" : "Prev",
      previousAriaLabel: zh ? "上一页" : "Previous page",
      next: zh ? "下一页" : "Next",
      nextAriaLabel: zh ? "下一页" : "Next page",
      page: (current, count) => `${current} / ${count}`,
      pageSize: zh ? "每页" : "Per page",
      total: (count) => zh ? `${count.toLocaleString()} 项结果` : `${count.toLocaleString()} results`,
    }}
  />;
}
