"use client";

/**
 * Company "About" card for the stock-detail sidebar (below ActionBox).
 *
 * Fetches yfinance-sourced profile data progressively (the page never
 * blocks on it): shows a skeleton, then the name / sector·industry /
 * business summary. Hides entirely when the ticker has no profile (e.g.
 * delisted), so the sidebar stays clean rather than showing an empty card.
 *
 * key={ticker} on the parent remounts this on SPA navigation, so state
 * never bleeds across tickers.
 */

import { useEffect, useState } from "react";

import { fetchProfile, type CompanyProfile as Profile } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";

type Status = "loading" | "done" | "error";

export default function CompanyProfile({ ticker }: { ticker: string }) {
  const { locale } = useLocale();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [expanded, setExpanded] = useState(false);

  // Refetch on locale change so the summary switches zh ↔ en (the backend
  // returns summary_zh for lang=zh when a translation exists, else en).
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    fetchProfile(ticker, locale)
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        setStatus("done");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, locale]);

  const copy =
    locale === "zh"
      ? {
          title: "公司简介",
          showMore: "展开",
          showLess: "收起",
          employees: "员工",
          site: "官网",
          pendingZh: "中文翻译待补,以下为英文原文",
        }
      : {
          title: "About",
          showMore: "Show more",
          showLess: "Show less",
          employees: "Employees",
          site: "Website",
          pendingZh: "",
        };

  if (status === "loading") {
    return (
      <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 space-y-2">
        <div className="h-3 w-20 animate-pulse rounded bg-tm-bg-3" />
        <div className="h-3 w-full animate-pulse rounded bg-tm-bg-3" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-tm-bg-3" />
      </div>
    );
  }

  // No usable profile (all-null from backend, or fetch error) → hide the
  // card so the sidebar isn't cluttered with an empty shell.
  if (status === "error" || !profile || (!profile.name && !profile.summary)) {
    return null;
  }

  const subtitle = [profile.sector, profile.industry]
    .filter(Boolean)
    .join(" · ");
  const summary = profile.summary ?? "";
  const isLong = summary.length > 220;

  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 space-y-1.5">
      <div className="text-[10px] font-tm-mono uppercase tracking-wide text-tm-muted">
        {copy.title}
      </div>
      {profile.name ? (
        <div className="text-sm font-semibold text-tm-fg">{profile.name}</div>
      ) : null}
      {subtitle ? (
        <div className="text-xs text-tm-fg-2">{subtitle}</div>
      ) : null}
      {summary && locale === "zh" && profile.summary_lang === "en" ? (
        <div className="text-[10px] italic text-tm-muted">{copy.pendingZh}</div>
      ) : null}
      {summary ? (
        <p
          className={`text-xs leading-relaxed text-tm-fg-2 ${
            isLong && !expanded
              ? "line-clamp-4"
              : isLong
                ? "max-h-48 overflow-y-auto pr-1"
                : ""
          }`}
        >
          {summary}
        </p>
      ) : null}
      {isLong ? (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="text-[11px] text-tm-accent hover:underline"
        >
          {expanded ? copy.showLess : copy.showMore}
        </button>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-[10px] text-tm-muted">
        {profile.employees ? (
          <span>
            {copy.employees}: {profile.employees.toLocaleString()}
          </span>
        ) : null}
        {profile.country ? <span>{profile.country}</span> : null}
        {profile.website ? (
          <a
            href={profile.website}
            target="_blank"
            rel="noopener noreferrer"
            className="text-tm-accent hover:underline"
          >
            {copy.site}
          </a>
        ) : null}
      </div>
    </div>
  );
}
