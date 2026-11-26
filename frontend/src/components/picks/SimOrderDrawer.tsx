// frontend/src/components/picks/SimOrderDrawer.tsx
"use client";

import type { RatingCard } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmDrawer } from "@/components/tm/TmDrawer";
import SimOrderForm from "./SimOrderForm";
import { Disclaimer } from "./paper/PaperUi";
import { t } from "@/lib/i18n";
import type { PickOrderSource } from "./paper-order-source";

interface Props {
  readonly source: PickOrderSource;
  readonly card: RatingCard;
  readonly cash?: number;
  readonly onClose: () => void;
  readonly onOrderPlaced: () => void;
}

export default function SimOrderDrawer({ source, card, cash, onClose, onOrderPlaced }: Props) {
  const { locale } = useLocale();

  return (
    <TmDrawer
      open
      onClose={onClose}
      closeLabel={t(locale, "sim.close")}
      eyebrow="PAPER.ORDER"
      title={locale === "zh" ? "模拟下单" : "Simulated Order"}
      description={
        locale === "zh"
          ? "在保留推荐上下文的同时创建模拟订单。"
          : "Create a paper order without losing the recommendation context."
      }
      width="sm"
    >
      <SimOrderForm
        fixedTicker={source.ticker}
        locale={locale}
        onPlaced={() => { onOrderPlaced(); onClose(); }}
        pickSource={source}
        initialSide={card.rating === "SELL" || card.rating === "UW" ? "sell" : "buy"}
        latestPrice={card.latest_price}
        priceDate={card.price_date}
        availableCash={cash}
      />
      <div className="mt-3">
        <Disclaimer />
      </div>
    </TmDrawer>
  );
}
