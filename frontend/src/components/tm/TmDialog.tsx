"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import clsx from "clsx";
import { TmIconButton } from "./TmButton";

interface TmDialogProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly eyebrow?: ReactNode;
  readonly headerAside?: ReactNode;
  readonly children: ReactNode;
  readonly closeLabel: string;
  readonly className?: string;
  readonly bodyClassName?: string;
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** Canonical workstation dialog with focus entry, trap, Escape and restore. */
export function TmDialog({
  open,
  onClose,
  title,
  description,
  eyebrow,
  headerAside,
  children,
  closeLabel,
  className,
  bodyClassName,
}: TmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
      );
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [onClose, open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-6 sm:p-10"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        tabIndex={-1}
        className={clsx(
          "flex max-h-[84vh] w-full max-w-[1040px] flex-col border border-tm-rule-2 bg-tm-bg shadow-2xl outline-none",
          className,
        )}
      >
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-tm-rule bg-tm-bg-2/45 px-5 py-4">
          <div className="min-w-0 flex-1">
            {eyebrow !== undefined && eyebrow !== null ? (
              <div className="font-tm-mono text-[10px] uppercase tracking-[0.16em] text-tm-accent">
                {eyebrow}
              </div>
            ) : null}
            <h2 id={titleId} className="mt-1 text-[18px] font-semibold text-tm-fg">
              {title}
            </h2>
            {description !== undefined && description !== null ? (
              <p id={descriptionId} className="mt-1 truncate text-[11px] text-tm-muted">
                {description}
              </p>
            ) : null}
          </div>
          {headerAside}
          <TmIconButton
            ref={closeRef}
            onClick={onClose}
            label={closeLabel}
            icon={<X className="h-4 w-4" strokeWidth={1.75} />}
            variant="secondary"
            size="md"
            className="w-8"
          />
        </header>
        <div className={clsx("min-h-0 flex-1 overflow-y-auto p-4", bodyClassName)}>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
