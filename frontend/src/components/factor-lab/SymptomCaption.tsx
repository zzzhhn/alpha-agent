import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

interface SymptomCaptionProps {
  readonly locale: Locale;
  readonly symptom: string;
}

export function SymptomCaption({ locale, symptom }: SymptomCaptionProps) {
  if (!symptom) return null;
  return (
    <div className="border-t border-tm-rule pt-2 font-tm-mono text-[10px] text-tm-muted">
      <span className="uppercase tracking-wider">
        {t(locale, "factorLab.decision.symptom")}
      </span>
      <span className="ml-2">{symptom}</span>
    </div>
  );
}
