export type DateTimeYear = "none" | "two-digit" | "numeric";

export interface FormatUtc8DateTimeOptions {
  readonly year?: DateTimeYear;
  readonly seconds?: boolean;
  readonly fallback?: string;
}

/**
 * Format an API timestamp deterministically in the product's operating
 * timezone. Manual UTC arithmetic keeps the server-rendered string identical
 * to the browser string, regardless of the Vercel region or browser locale.
 */
export function formatUtc8DateTime(
  raw: string | null | undefined,
  options: FormatUtc8DateTimeOptions = {},
): string {
  const fallback = options.fallback ?? "—";
  if (!raw) return fallback;

  const instant = new Date(raw);
  if (Number.isNaN(instant.getTime())) return fallback;

  const utc8 = new Date(instant.getTime() + 8 * 60 * 60 * 1000);
  const pad = (value: number) => String(value).padStart(2, "0");
  const year = utc8.getUTCFullYear();
  const date = `${pad(utc8.getUTCMonth() + 1)}/${pad(utc8.getUTCDate())}`;
  const yearPrefix =
    options.year === "numeric"
      ? `${year}/`
      : options.year === "two-digit"
        ? `${pad(year % 100)}/`
        : "";
  const time = `${pad(utc8.getUTCHours())}:${pad(utc8.getUTCMinutes())}`;
  const seconds = options.seconds ? `:${pad(utc8.getUTCSeconds())}` : "";

  return `${yearPrefix}${date} ${time}${seconds} UTC+8`;
}
