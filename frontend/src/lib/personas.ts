// frontend/src/lib/personas.ts
//
// Persona metadata that previously came from GET /api/stock/personas. The
// endpoint just rendered a static dictionary (alpha_agent/personas/registry.py
// → PERSONAS), so embedding the same 7-entry table here removes one network
// round-trip per stock-page load (100-200ms saved on cold visits).
//
// Drift discipline: when adding a persona to the backend registry, mirror
// it here. The set is small + bounded by deliberate product decisions, not
// data-driven, so the coupling cost is acceptable.

export interface PersonaMeta {
  name: string;
  label: string;
  signals: string[];
}

export type PersonaLocale = "zh" | "en";

const PERSONAS_BY_LOCALE: Record<PersonaLocale, PersonaMeta[]> = {
  zh: [
    { name: "technical", label: "技术派", signals: ["technicals", "premarket"] },
    { name: "news", label: "新闻派", signals: ["news"] },
    {
      name: "political",
      label: "政策派",
      signals: ["political_impact", "geopolitical_impact"],
    },
    { name: "options", label: "期权派", signals: ["options"] },
    { name: "insider", label: "内部人派", signals: ["insider"] },
    { name: "macro", label: "宏观派", signals: ["macro", "factor"] },
    {
      name: "risk",
      label: "风控派",
      signals: ["technicals", "options", "macro", "earnings"],
    },
  ],
  en: [
    {
      name: "technical",
      label: "Technical Analyst",
      signals: ["technicals", "premarket"],
    },
    { name: "news", label: "News Analyst", signals: ["news"] },
    {
      name: "political",
      label: "Political Analyst",
      signals: ["political_impact", "geopolitical_impact"],
    },
    { name: "options", label: "Options Analyst", signals: ["options"] },
    { name: "insider", label: "Insider Analyst", signals: ["insider"] },
    {
      name: "macro",
      label: "Macro Analyst",
      signals: ["macro", "factor"],
    },
    {
      name: "risk",
      label: "Risk Manager",
      signals: ["technicals", "options", "macro", "earnings"],
    },
  ],
};

export function getPersonas(locale: PersonaLocale): PersonaMeta[] {
  return PERSONAS_BY_LOCALE[locale];
}
