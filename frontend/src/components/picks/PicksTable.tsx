import type { RatingCard } from "@/lib/api/picks";
import PickRow from "./PickRow";

const TH = "px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted select-none";

export default function PicksTable({ picks }: { picks: RatingCard[] }) {
  if (picks.length === 0) {
    return (
      <div className="px-3 py-6 font-tm-mono text-[11px] text-tm-muted">
        No picks yet — cron hasn&apos;t run.
      </div>
    );
  }

  return (
    <table className="w-full border-collapse">
      <thead className="border-b border-tm-rule bg-tm-bg-2">
        <tr>
          <th className={`${TH} text-left w-8`}>#</th>
          <th className={`${TH} text-left`}>Ticker</th>
          <th className={`${TH} text-left`}>Rating</th>
          <th className={`${TH} text-right`}>Composite</th>
          <th className={`${TH} text-right`}>Confidence</th>
          <th className={`${TH} text-left`}>Top drivers</th>
        </tr>
      </thead>
      <tbody>
        {picks.map((card, i) => (
          <PickRow key={card.ticker} rank={i + 1} card={card} />
        ))}
      </tbody>
    </table>
  );
}
