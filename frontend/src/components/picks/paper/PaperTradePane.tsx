"use client";

// PaperTradePane — dedicated "下单" tab. Split out of the old PaperTab
// overview screen so overview doesn't have to carry KPIs + positions + an
// order ticket on one screen (cognitive-load fix #2).
import SimOrderForm from "../SimOrderForm";
import { useLocale } from "@/components/layout/LocaleProvider";
import { Disclaimer } from "./PaperUi";

export default function PaperTradePane({ onPlaced }: { readonly onPlaced: () => void }) {
  const { locale } = useLocale();
  return (
    <div className="flex flex-col gap-4 px-3 py-3">
      <SimOrderForm locale={locale} onPlaced={onPlaced} />
      <Disclaimer />
    </div>
  );
}
