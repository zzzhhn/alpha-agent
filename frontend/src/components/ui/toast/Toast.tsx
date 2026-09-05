"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useContext } from "react";
import { ToastContext, type ToastItem } from "./ToastProvider";
import { TmButton, TmIconButton } from "@/components/tm/TmButton";
import { useLocale } from "@/components/layout/LocaleProvider";

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
  return <ToastView item={item} onDismiss={() => ctx.dismiss(item.id)} />;
}

export function ToastView({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const { locale } = useLocale();
  const style = _styles[item.kind];
  return (
    <div
      role={item.kind === "error" ? "alert" : "status"}
      className={`flex w-full max-w-[480px] items-start gap-3 rounded-[2px] border ${style.border} bg-tm-bg-2 px-3 py-2 shadow-[var(--tm-shadow-floating)]`}
    >
      <div className="mt-0.5">{style.icon}</div>
      <div className="min-w-0 flex-1 break-words text-xs leading-5 text-tm-fg">{item.message}</div>
      {item.action && (
        <TmButton variant="ghost" size="xs"
          onClick={() => {
            item.action!.onClick();
            onDismiss();
          }}
          className="shrink-0"
        >
          {item.action.label}
        </TmButton>
      )}
      <TmIconButton onClick={onDismiss} label={locale === "zh" ? "关闭通知" : "Dismiss notification"}
        size="xs" icon={<X className="h-3.5 w-3.5" strokeWidth={1.75} />} />
    </div>
  );
}
