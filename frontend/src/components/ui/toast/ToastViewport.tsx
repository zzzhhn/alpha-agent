"use client";

import { useContext } from "react";
import { ToastContext } from "./ToastProvider";
import { Toast } from "./Toast";

export function ToastViewport() {
  const ctx = useContext(ToastContext);
  if (!ctx) return null;
  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
    >
      {ctx.items.map((item) => (
        <div key={item.id} className="pointer-events-auto">
          <Toast item={item} />
        </div>
      ))}
    </div>
  );
}
