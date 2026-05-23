"use client";

import { useContext } from "react";
import { ToastContext, type ToastAction } from "./ToastProvider";

interface ToastOptions {
  duration?: number;
  action?: ToastAction;
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be called inside <ToastProvider>");
  }
  return {
    toast: {
      success: (message: string, opts?: ToastOptions) =>
        ctx.enqueue({
          kind: "success",
          message,
          duration: opts?.duration ?? 4000,
          action: opts?.action,
        }),
      error: (message: string, opts?: ToastOptions) =>
        ctx.enqueue({
          kind: "error",
          message,
          duration: opts?.duration ?? 0, // sticky by default
          action: opts?.action,
        }),
      info: (message: string, opts?: ToastOptions) =>
        ctx.enqueue({
          kind: "info",
          message,
          duration: opts?.duration ?? 3000,
          action: opts?.action,
        }),
      dismiss: (id: string) => ctx.dismiss(id),
    },
  };
}
