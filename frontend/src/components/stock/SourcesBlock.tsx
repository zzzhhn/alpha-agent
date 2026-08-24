"use client";

import type { RatingCard } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
} from "@/components/tm/TmTable";

export default function SourcesBlock({ card }: { card: RatingCard }) {
  const { locale } = useLocale();
  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-2 text-tm-fg">{t(locale, "sources.title")}</h2>
      <TmTableFrame>
        <TmTable
          density="compact"
          caption={t(locale, "sources.title")}
          className="text-xs"
        >
          <TmTableHead>
            <TmTableRow>
              <TmTableHeaderCell className="px-2 py-1">{t(locale, "sources.col_signal")}</TmTableHeaderCell>
              <TmTableHeaderCell className="px-2 py-1">{t(locale, "sources.col_source")}</TmTableHeaderCell>
              <TmTableHeaderCell className="px-2 py-1">{t(locale, "sources.col_timestamp")}</TmTableHeaderCell>
            </TmTableRow>
          </TmTableHead>
          <TmTableBody>
          {card.breakdown.map((b) => (
            <TmTableRow key={b.signal}>
              <TmTableCell className="px-2 py-1 text-tm-fg">{b.signal}</TmTableCell>
              <TmTableCell className="px-2 py-1 text-tm-muted">{b.source}</TmTableCell>
              <TmTableCell className="px-2 py-1 text-tm-muted">
                {new Date(b.timestamp).toLocaleString()}
              </TmTableCell>
            </TmTableRow>
          ))}
          </TmTableBody>
        </TmTable>
      </TmTableFrame>
    </section>
  );
}
