"use client";

/**
 * First-visit onboarding banner (P2-3). A dismissable, non-blocking strip
 * shown on the default landing page that orients a new user to the core
 * loop and flags that LLM features need a key. Dismissal persists in
 * localStorage so it shows once.
 *
 * Deliberately NOT a multi-step modal wizard — for a single-operator tool
 * a one-glance banner beats an interruptive flow.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { X, Compass } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";

const DISMISS_KEY = "alphacore.onboarding.dismissed.v1";

export default function OnboardingBanner() {
  const { locale } = useLocale();
  // Start hidden; reveal only after the post-mount localStorage check, so
  // a returning user never sees a flash of the banner.
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      if (!window.localStorage.getItem(DISMISS_KEY)) setShow(true);
    } catch {
      // storage disabled — just don't show (no nag without a way to dismiss)
    }
  }, []);

  function dismiss() {
    setShow(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, new Date().toISOString());
    } catch {
      // ignore — banner stays dismissed for this session regardless
    }
  }

  if (!show) return null;

  const copy =
    locale === "zh"
      ? {
          title: "欢迎使用 AlphaCore",
          steps: [
            "在 因子 Alpha (Hypothesis Lab) 用自然语言研究因子",
            "回测 → 保存到 Zoo → 选股 / 浏览今日推荐",
            "Rich Brief、分析师视角等 LLM 功能需在 Settings 配置 API Key",
          ],
          settings: "去 Settings 配置 Key",
          dismiss: "知道了",
        }
      : {
          title: "Welcome to AlphaCore",
          steps: [
            "Research factors in natural language in Alpha (Hypothesis Lab)",
            "Backtest → save to Zoo → screen stocks / browse Picks",
            "LLM features (Rich Brief, Personas) need an API key in Settings",
          ],
          settings: "Configure key in Settings",
          dismiss: "Got it",
        };

  return (
    <div className="mx-4 mt-3 rounded border border-tm-accent/40 bg-tm-accent/5 px-4 py-3">
      <div className="flex items-start gap-3">
        <Compass
          aria-hidden
          className="mt-0.5 h-4 w-4 shrink-0 text-tm-accent"
          strokeWidth={1.75}
        />
        <div className="flex-1 space-y-1.5">
          <div className="text-sm font-semibold text-tm-fg">{copy.title}</div>
          <ol className="list-decimal space-y-0.5 pl-4 text-xs text-tm-fg-2">
            {copy.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
          <Link
            href="/settings"
            className="inline-block text-xs text-tm-accent hover:underline"
          >
            {copy.settings}
          </Link>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label={copy.dismiss}
          title={copy.dismiss}
          className="shrink-0 text-tm-muted transition-colors hover:text-tm-fg"
        >
          <X className="h-4 w-4" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}
