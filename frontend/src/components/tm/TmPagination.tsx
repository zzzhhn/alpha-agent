"use client";

import { useEffect, type ChangeEvent, type ReactNode } from "react";
import clsx from "clsx";
import { TmButton } from "./TmButton";

export interface TmPaginationLabels {
  /** Accessible name for the pagination landmark. */
  readonly navigation: string;
  readonly previous: ReactNode;
  readonly previousAriaLabel: string;
  readonly next: ReactNode;
  readonly nextAriaLabel: string;
  readonly page: (currentPage: number, pageCount: number) => ReactNode;
  readonly pageSize: ReactNode;
  readonly total: (totalItems: number) => ReactNode;
}

export interface TmPaginationProps {
  readonly page: number;
  readonly pageSize: number;
  readonly totalItems: number;
  readonly pageSizeOptions?: readonly number[];
  readonly labels: TmPaginationLabels;
  readonly onPageChange: (page: number) => void;
  readonly onPageSizeChange: (pageSize: number) => void;
  readonly disabled?: boolean;
  readonly loading?: boolean;
  readonly className?: string;
}

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

function positiveInteger(value: number, fallback: number): number {
  return Number.isFinite(value) && value > 0 ? Math.max(1, Math.floor(value)) : fallback;
}

/**
 * TmPagination: compact, controlled pagination for workstation tables.
 *
 * All visible copy is supplied by the caller so the same primitive can be
 * rendered in either locale. The page count is derived from totalItems and
 * pageSize; callers remain responsible for fetching and storing the page.
 */
export function TmPagination({
  page,
  pageSize,
  totalItems,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  labels,
  onPageChange,
  onPageSizeChange,
  disabled = false,
  loading = false,
  className,
}: TmPaginationProps) {
  const safePageSize = positiveInteger(pageSize, DEFAULT_PAGE_SIZE_OPTIONS[0]);
  const safeTotalItems = Number.isFinite(totalItems)
    ? Math.max(0, Math.floor(totalItems))
    : 0;
  const pageCount = Math.max(1, Math.ceil(safeTotalItems / safePageSize));
  const currentPage = Math.min(
    Math.max(positiveInteger(page, 1), 1),
    pageCount,
  );
  const isDisabled = disabled || loading;
  const options = Array.from(
    new Set(
      [...pageSizeOptions, safePageSize]
        .filter((option) => Number.isFinite(option) && option > 0)
        .map((option) => Math.floor(option)),
    ),
  ).sort((left, right) => left - right);

  useEffect(() => {
    if (!isDisabled && positiveInteger(page, 1) !== currentPage) {
      onPageChange(currentPage);
    }
  }, [currentPage, isDisabled, onPageChange, page]);

  function changePage(nextPage: number) {
    if (isDisabled || nextPage === currentPage) return;
    onPageChange(Math.min(Math.max(nextPage, 1), pageCount));
  }

  function changePageSize(nextPageSize: number) {
    if (isDisabled || !options.includes(nextPageSize)) return;
    onPageSizeChange(nextPageSize);
    if (currentPage !== 1) onPageChange(1);
  }

  return (
    <nav
      aria-label={labels.navigation}
      aria-busy={loading || undefined}
      className={clsx(
        "flex w-full min-w-0 flex-wrap items-center gap-x-2 gap-y-1 border-t border-tm-rule bg-tm-bg px-3 py-2 font-tm-mono text-[10px] text-tm-muted sm:flex-nowrap",
        className,
      )}
    >
      <span
        aria-live="polite"
        className="min-w-[6rem] flex-[1_1_8rem] break-words tabular-nums leading-4 text-tm-fg-2"
      >
        {labels.total(safeTotalItems)}
      </span>

      <div className="flex min-w-0 shrink-0 flex-wrap items-center gap-1.5">
        <TmButton
          variant="secondary"
          size="xs"
          aria-label={labels.previousAriaLabel}
          onClick={() => changePage(currentPage - 1)}
          disabled={isDisabled || currentPage <= 1}
        >
          {labels.previous}
        </TmButton>

        <span
          aria-live="polite"
          className="min-w-[4.5rem] shrink-0 text-center tabular-nums text-tm-fg"
        >
          {labels.page(currentPage, pageCount)}
        </span>

        <TmButton
          variant="secondary"
          size="xs"
          aria-label={labels.nextAriaLabel}
          onClick={() => changePage(currentPage + 1)}
          disabled={isDisabled || currentPage >= pageCount}
        >
          {labels.next}
        </TmButton>

        {options.length > 1 ? (
          <label className="flex min-h-7 shrink-0 items-center gap-1 text-tm-muted">
            <span>{labels.pageSize}</span>
            <select
              value={safePageSize}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                changePageSize(Number(event.target.value))
              }
              disabled={isDisabled}
              className="h-7 min-w-[3.5rem] rounded-[2px] border border-tm-rule bg-tm-bg-2 px-1.5 font-tm-mono text-[10px] text-tm-fg disabled:cursor-not-allowed disabled:opacity-50"
            >
              {options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
    </nav>
  );
}
