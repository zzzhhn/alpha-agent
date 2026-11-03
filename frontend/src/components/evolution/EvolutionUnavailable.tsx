"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { TmButton } from "@/components/tm/TmButton";
import type { Locale } from "@/lib/i18n";

export function EvolutionUnavailable({ locale, message }: { locale: Locale; message?: string }) {
  const zh = locale === "zh";
  const router = useRouter();
  const [retrying, startTransition] = useTransition();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 text-xs">
      <span className="text-tm-warn">{message ?? (zh ? "数据暂不可用" : "Data unavailable")}</span>
      <TmButton size="xs" variant="secondary" disabled={retrying} onClick={() => startTransition(() => router.refresh())}>
        {retrying ? (zh ? "刷新中" : "Refreshing") : (zh ? "刷新页面" : "Refresh page")}
      </TmButton>
    </div>
  );
}
