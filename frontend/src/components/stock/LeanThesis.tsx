import type { RatingCard } from "@/lib/api/picks";
import { renderLeanThesis } from "@/lib/thesis";

export default function LeanThesis({ card }: { card: RatingCard }) {
  const t = renderLeanThesis(card);
  return (
    <section className="grid grid-cols-2 gap-4">
      <ThesisBlock title="Bull case" tone="bull" items={t.bull} />
      <ThesisBlock title="Bear case" tone="bear" items={t.bear} />
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
  const accent =
    tone === "bull" ? "border-emerald-500/40" : "border-rose-500/40";
  return (
    <div className={`rounded border ${accent} p-4`}>
      <h3 className="font-semibold mb-2">{title}</h3>
      <ul className="space-y-1.5 text-sm">
        {items.map((it, i) => (
          <li key={i}>• {it}</li>
        ))}
      </ul>
    </div>
  );
}
