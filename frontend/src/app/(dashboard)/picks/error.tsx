"use client";

// Route-level error boundary for /picks. Without this, any render error in
// the picks subtree (a malformed RatingCard, a failed fetchPicks, etc.)
// bubbles to Next.js's built-in "Application error: a client-side exception"
// white screen. This catches it and offers a retry instead.
import { useEffect } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";

export default function PicksError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { locale } = useLocale();

  useEffect(() => {
    // Keep the real error visible to anyone with the console open.
    console.error("picks route error:", error);
  }, [error]);

  const copy =
    locale === "zh"
      ? {
          title: "Picks 加载失败",
          body: "这个页面遇到了一个错误,可能是数据源暂时不可用。可以点重试,或稍后再来。",
          retry: "重试",
        }
      : {
          title: "Picks failed to load",
          body: "This page hit an error, possibly a temporarily unavailable data source. Try again, or come back later.",
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
