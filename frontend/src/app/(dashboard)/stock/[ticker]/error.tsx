"use client";

// Route-level error boundary for /stock/[ticker]. Without it, any error the
// page rethrows (a backend 5xx, a network failure) falls through to Next's
// built-in "server-side exception" screen. notFound() is NOT caught here -
// it has its own not-found boundary - so a genuinely missing ticker still
// renders the 404 page rather than this.
import { useEffect, useState } from "react";
import { getLocaleFromStorage } from "@/lib/i18n";

export default function StockError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [locale, setLocale] = useState<"zh" | "en">("zh");

  useEffect(() => {
    setLocale(getLocaleFromStorage());
    console.error("stock route error:", error);
  }, [error]);

  const copy =
    locale === "zh"
      ? {
          title: "股票详情加载失败",
          body: "这个页面遇到了一个错误,可能是后端暂时不可用。可以点重试,或稍后再来。",
          retry: "重试",
        }
      : {
          title: "Stock detail failed to load",
          body: "This page hit an error, possibly a temporarily unavailable backend. Try again, or come back later.",
          retry: "Retry",
        };

  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="font-tm-mono text-[13px] font-semibold text-tm-fg">
        {copy.title}
      </div>
      <p className="max-w-sm font-tm-mono text-[11px] leading-relaxed text-tm-muted">
        {copy.body}
      </p>
      <button
        onClick={reset}
        className="mt-1 rounded border border-tm-rule px-3 py-1.5 font-tm-mono text-[11px] text-tm-accent transition-colors hover:bg-tm-bg-2"
      >
        {copy.retry}
      </button>
    </div>
  );
}
