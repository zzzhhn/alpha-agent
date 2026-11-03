"use client";

import { TmPagination } from "@/components/tm/TmPagination";
import type { Locale } from "@/lib/i18n";

import { EVOLUTION_PAGE_SIZE } from "./review-state";

export function EvolutionPagination({ locale, label, page, total, onPageChange }: {
  locale: Locale; label: string; page: number; total: number; onPageChange: (page: number) => void;
}) {
  if (total <= EVOLUTION_PAGE_SIZE) return null;
  const zh = locale === "zh";
  return (
    <TmPagination page={page} pageSize={EVOLUTION_PAGE_SIZE} totalItems={total} pageSizeOptions={[EVOLUTION_PAGE_SIZE]}
      onPageChange={onPageChange} onPageSizeChange={() => {}}
      labels={{
        navigation: label, previous: "←", next: "→",
        previousAriaLabel: zh ? "上一页" : "Previous page", nextAriaLabel: zh ? "下一页" : "Next page",
        page: (current, count) => `${current} / ${count}`, pageSize: zh ? "每页" : "Per page",
        total: (n) => zh ? `已加载 ${n} 条` : `${n} loaded`,
      }}
    />
  );
}
