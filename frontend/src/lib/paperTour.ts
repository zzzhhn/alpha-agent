/**
 * paperTour — driver.js onboarding tour for /paper. 6 steps per
 * docs/superpowers/specs/2026-07-26-paper-trading-v2-design.md
 * "Onboarding": orientation, fill rules, first-order entry (cross-page,
 * no element to highlight), the three panel tabs (highlighted in
 * sequence), the honesty label, and a CTA that lands on the trade tab.
 *
 * Steps target stable `data-tour="..."` selectors rather than class
 * names, so a future style pass can't silently break the tour (see
 * PaperScreen.tsx tab chips and PaperUi.tsx Disclaimer).
 *
 * CSS (driver.js base + tm- theme override) is imported by the caller
 * (PaperScreen.tsx), not here — Next's App Router only reliably bundles
 * CSS imports that originate from component files.
 */
import { driver, type DriveStep } from "driver.js";
import { t, type Locale } from "@/lib/i18n";

export type PaperTourTab = "overview" | "trade" | "curve" | "orders";

const SEEN_KEY = "paper_tour_seen_v1";

export function hasSeenPaperTour(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(SEEN_KEY) === "1";
}

function markPaperTourSeen(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SEEN_KEY, "1");
}

function sel(tourKey: string): string {
  return `[data-tour="${tourKey}"]`;
}

function buildSteps(locale: Locale, changeTab: (tab: PaperTourTab) => void): DriveStep[] {
  return [
    {
      popover: {
        title: t(locale, "sim.tour.step1_title"),
        description: t(locale, "sim.tour.step1_desc"),
      },
    },
    {
      element: sel("paper-tab-trade"),
      popover: {
        title: t(locale, "sim.tour.step2_title"),
        description: t(locale, "sim.tour.step2_desc"),
      },
    },
    {
      popover: {
        title: t(locale, "sim.tour.step3_title"),
        description: t(locale, "sim.tour.step3_desc"),
      },
    },
    {
      element: sel("paper-tab-overview"),
      popover: {
        title: t(locale, "sim.tour.step4_overview_title"),
        description: t(locale, "sim.tour.step4_overview_desc"),
      },
    },
    {
      element: sel("paper-tab-curve"),
      popover: {
        title: t(locale, "sim.tour.step4_curve_title"),
        description: t(locale, "sim.tour.step4_curve_desc"),
      },
    },
    {
      element: sel("paper-tab-orders"),
      popover: {
        title: t(locale, "sim.tour.step4_orders_title"),
        description: t(locale, "sim.tour.step4_orders_desc"),
      },
    },
    {
      element: sel("sim-disclaimer"),
      popover: {
        title: t(locale, "sim.tour.step5_title"),
        description: t(locale, "sim.tour.step5_desc"),
      },
    },
    {
      element: sel("paper-tab-trade"),
      popover: {
        title: t(locale, "sim.tour.step6_title"),
        description: t(locale, "sim.tour.step6_desc"),
        nextBtnText: t(locale, "sim.tour.done_btn"),
        onNextClick: (_element, _step, opts) => {
          changeTab("trade");
          opts.driver.destroy();
        },
      },
    },
  ];
}

/** Starts (or replays) the tour. Marks it seen on any exit path — Done,
 *  the close button, overlay click, or Escape — so "?" is the only way
 *  back in after the first run. */
export function startPaperTour(locale: Locale, changeTab: (tab: PaperTourTab) => void): void {
  const tourDriver = driver({
    steps: buildSteps(locale, changeTab),
    animate: true,
    stageRadius: 0,
    allowClose: true,
    overlayOpacity: 0.7,
    showProgress: true,
    progressText: t(locale, "sim.tour.progress"),
    nextBtnText: t(locale, "sim.tour.next_btn"),
    prevBtnText: t(locale, "sim.tour.prev_btn"),
    doneBtnText: t(locale, "sim.tour.done_btn"),
    onDestroyed: () => {
      markPaperTourSeen();
    },
  });
  tourDriver.drive();
}
