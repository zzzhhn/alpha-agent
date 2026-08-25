"use client";

import {
  type ReactNode,
  type HTMLAttributes,
  type TableHTMLAttributes,
  type ThHTMLAttributes,
  type TdHTMLAttributes,
} from "react";
import clsx from "clsx";

export function TmTableFrame({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("min-w-0 overflow-x-auto", className)} {...rest} />;
}

interface TmTableProps extends TableHTMLAttributes<HTMLTableElement> {
  readonly density?: "compact" | "standard";
  readonly caption?: ReactNode;
}

export function TmTable({ density = "standard", caption, className, children, ...rest }: TmTableProps) {
  return (
    <table
      data-density={density}
      className={clsx(
        "w-full border-collapse font-tm-mono text-xs",
        density === "compact"
          ? "[&_td]:h-8 [&_th[scope=row]]:h-8"
          : "[&_td]:h-9 [&_th[scope=row]]:h-9",
        className,
      )}
      {...rest}
    >
      {caption !== undefined && caption !== null ? (
        <caption className="sr-only">{caption}</caption>
      ) : null}
      {children}
    </table>
  );
}

export function TmTableHead({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={clsx(
        "bg-tm-bg-2 font-tm-mono text-xs uppercase tracking-[0.06em] text-tm-muted [&_tr]:bg-tm-bg-2 [&_tr]:hover:bg-tm-bg-2",
        className,
      )}
      {...rest}
    />
  );
}

export function TmTableBody({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={className} {...rest} />;
}

interface TmTableRowProps extends HTMLAttributes<HTMLTableRowElement> {
  readonly selected?: boolean;
}

export function TmTableRow({ selected = false, className, ...rest }: TmTableRowProps) {
  return (
    <tr
      aria-selected={selected || undefined}
      data-selected={selected || undefined}
      className={clsx(
        "border-b border-tm-rule bg-tm-bg transition-colors last:border-b-0 hover:bg-tm-bg-2",
        selected && "bg-tm-accent-soft hover:bg-tm-accent-soft",
        className,
      )}
      {...rest}
    />
  );
}

interface Alignable {
  readonly textAlign?: "left" | "center" | "right";
}

const ALIGN = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
} as const;

interface TmTableHeaderCellProps extends ThHTMLAttributes<HTMLTableCellElement>, Alignable {
  readonly sortDirection?: "ascending" | "descending" | "none";
}

export function TmTableHeaderCell({
  textAlign = "left",
  sortDirection,
  className,
  scope = "col",
  ...rest
}: TmTableHeaderCellProps) {
  return (
    <th
      scope={scope}
      aria-sort={sortDirection}
      className={clsx("px-3 py-2 font-semibold", ALIGN[textAlign], className)}
      {...rest}
    />
  );
}

interface TmTableCellProps extends TdHTMLAttributes<HTMLTableCellElement>, Alignable {
  readonly numeric?: boolean;
}

export function TmTableCell({
  textAlign = "left",
  numeric = false,
  className,
  ...rest
}: TmTableCellProps) {
  return (
    <td
      className={clsx(
        "px-3 text-tm-fg-2",
        ALIGN[textAlign],
        numeric && "tabular-nums text-tm-fg",
        className,
      )}
      {...rest}
    />
  );
}

interface TmTableRowHeaderProps extends ThHTMLAttributes<HTMLTableCellElement>, Alignable {}

export function TmTableRowHeader({
  textAlign = "left",
  className,
  scope = "row",
  ...rest
}: TmTableRowHeaderProps) {
  return (
    <th
      scope={scope}
      className={clsx("px-3 font-medium text-tm-fg", ALIGN[textAlign], className)}
      {...rest}
    />
  );
}
