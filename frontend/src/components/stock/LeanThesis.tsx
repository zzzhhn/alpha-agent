"use client";

import { useEffect, useState } from "react";
import type { RatingCard } from "@/lib/api/picks";
import { renderLeanThesis } from "@/lib/thesis";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

export default function LeanThesis({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);
  const thesis = renderLeanThesis(card);
  return (
    <section className="grid grid-cols-2 gap-4">
      <ThesisBlock title={t(locale, "stock.thesis.bull")} tone="bull" items={thesis.bull} />
      <ThesisBlock title={t(locale, "stock.thesis.bear")} tone="bear" items={thesis.bear} />
    </section>
  );
}

function ThesisBlock({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "bull" | "bear";
  items: string[];
}) {
  const accentBorder = tone === "bull" ? "border-tm-pos" : "border-tm-neg";
  const accentTitle = tone === "bull" ? "text-tm-pos" : "text-tm-neg";
  return (
    <div className={`rounded border ${accentBorder} bg-tm-bg-2 p-4`}>
      <h3 className={`font-semibold mb-2 ${accentTitle}`}>{title}</h3>
      <ul className="space-y-1.5 text-sm text-tm-fg">
        {items.map((it, i) => (
          <li key={i}>• {it}</li>
        ))}
      </ul>
    </div>
  );
}
