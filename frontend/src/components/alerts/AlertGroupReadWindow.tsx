import type { AlertInboxItem } from "@/lib/api/alertsFeed";
import type { Locale } from "@/lib/i18n";

export function AlertGroupReadWindow({ item, locale, formatTime }: {
  item: Pick<AlertInboxItem, "occurrences" | "first_seen_at" | "last_seen_at" | "created_at">;
  locale: Locale;
  formatTime: (value: string) => string;
}) {
  const count = item.occurrences ?? 1;
  if (count < 2) return null;
  const first = item.first_seen_at ?? item.created_at;
  const last = item.last_seen_at ?? item.created_at;
  const zh = locale === "zh";
  return (
    <p className="mt-2 text-xs leading-5 text-tm-muted">
      {zh ? "美东同日 · 首次 " : "Same New York date · First "}
      <time dateTime={first}>{formatTime(first)}</time>
      {zh ? " · 最后 " : " · Last "}
      <time dateTime={last}>{formatTime(last)}</time>
      {zh ? "。处理和撤销只覆盖本次读取的 " : ". Actions and undo cover the "}
      {count}
      {zh ? " 条。" : " alerts in this read."}
    </p>
  );
}
