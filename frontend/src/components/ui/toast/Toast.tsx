"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useContext } from "react";
import { ToastContext, type ToastItem } from "./ToastProvider";

// Tokens used: tm-pos, tm-neg, tm-rule, tm-bg-2, tm-fg, tm-fg-2, tm-accent
// (tm-card and tm-line from spec do not exist; mapped to tm-bg-2 and tm-rule)
// (tm-fg-1 from spec does not exist; mapped to tm-fg)
const _styles = {
  success: {
    border: "border-tm-pos/40",
    bg: "bg-tm-pos/10",
    icon: (
      <CheckCircle2 className="h-4 w-4 text-tm-pos" strokeWidth={1.75} />
    ),
  },
  error: {
    border: "border-tm-neg/40",
    bg: "bg-tm-neg/10",
    icon: (
      <AlertCircle className="h-4 w-4 text-tm-neg" strokeWidth={1.75} />
    ),
  },
  info: {
    border: "border-tm-rule",
    bg: "bg-tm-bg-2",
    icon: (
      <Info className="h-4 w-4 text-tm-fg-2" strokeWidth={1.75} />
    ),
  },
};

export function Toast({ item }: { item: ToastItem }) {
  const ctx = useContext(ToastContext);
  if (!ctx) return null;
  const style = _styles[item.kind];
  return (
    <div
      role={item.kind === "error" ? "alert" : "status"}
      className={`flex min-w-[280px] max-w-[480px] items-start gap-3 rounded border ${style.border} ${style.bg} px-3 py-2 shadow-sm`}
    >
      <div className="mt-0.5">{style.icon}</div>
      <div className="flex-1 text-sm text-tm-fg">{item.message}</div>
      {item.action && (
        <button
          onClick={() => {
            item.action!.onClick();
            ctx.dismiss(item.id);
          }}
          className="text-sm font-semibold text-tm-accent hover:underline"
        >
          {item.action.label}
        </button>
      )}
      <button
        onClick={() => ctx.dismiss(item.id)}
        aria-label="Dismiss"
        className="text-tm-fg-2 hover:text-tm-fg"
      >
        <X className="h-3.5 w-3.5" strokeWidth={1.75} />
      </button>
    </div>
  );
}
