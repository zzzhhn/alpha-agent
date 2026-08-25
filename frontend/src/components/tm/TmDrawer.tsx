"use client";

import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import clsx from "clsx";
import { TmIconButton } from "./TmButton";
import { useTmModalFocus } from "./useTmModalFocus";

type DrawerSide = "left" | "right";
type DrawerWidth = "sm" | "md" | "lg" | "xl";

interface TmDrawerProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly eyebrow?: ReactNode;
  readonly children: ReactNode;
  readonly closeLabel: string;
  readonly side?: DrawerSide;
  readonly width?: DrawerWidth;
  readonly className?: string;
  readonly bodyClassName?: string;
  readonly footer?: ReactNode;
}

const WIDTHS: Record<DrawerWidth, string> = {
  sm: "w-[320px]",
  md: "w-[420px]",
  lg: "w-[560px]",
  xl: "w-[720px]",
};

/** Canonical modal side panel for contextual work without losing page state. */
export function TmDrawer({
  open,
  onClose,
  title,
  description,
  eyebrow,
  children,
  closeLabel,
  side = "right",
  width = "md",
  className,
  bodyClassName,
  footer,
}: TmDrawerProps) {
  const titleId = useId();
  const descriptionId = useId();
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useTmModalFocus(open, onClose, drawerRef, closeRef);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className={clsx(
        "fixed inset-0 z-[60] flex bg-black/70",
        side === "right" ? "justify-end" : "justify-start",
      )}
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        tabIndex={-1}
        className={clsx(
          "flex h-full max-w-[calc(100vw-24px)] flex-col bg-tm-bg shadow-2xl outline-none",
          WIDTHS[width],
          side === "right" ? "border-l border-tm-rule-2" : "border-r border-tm-rule-2",
          className,
        )}
      >
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-tm-rule bg-tm-bg-2/45 px-4 py-3">
          <div className="min-w-0 flex-1">
            {eyebrow !== undefined && eyebrow !== null ? (
              <div className="font-tm-mono text-xs uppercase tracking-[0.16em] text-tm-accent">
                {eyebrow}
              </div>
            ) : null}
            <h2 id={titleId} className="mt-1 text-[16px] font-semibold text-tm-fg">
              {title}
            </h2>
            {description !== undefined && description !== null ? (
              <p id={descriptionId} className="mt-1 text-xs leading-5 text-tm-muted">
                {description}
              </p>
            ) : null}
          </div>
          <TmIconButton
            ref={closeRef}
            onClick={onClose}
            label={closeLabel}
            icon={<X className="h-4 w-4" strokeWidth={1.75} />}
            variant="secondary"
            size="md"
          />
        </header>
        <div className={clsx("min-h-0 flex-1 overflow-y-auto p-4", bodyClassName)}>
          {children}
        </div>
        {footer !== undefined && footer !== null ? (
          <footer className="shrink-0 border-t border-tm-rule bg-tm-bg-2/45 p-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
