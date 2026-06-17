// frontend/src/lib/signal-horizons.ts
// Native forward horizon (trading days) per signal. MUST mirror
// alpha_agent/signals/horizons.py SIGNAL_HORIZON_DAYS. Surfaced in the UI so a
// signal's IC (computed at a reference horizon) can be read against the horizon
// it actually operates on (council #4): factor is a 60d signal, so its 5d IC
// should not be over-interpreted.
export const SIGNAL_HORIZON_DAYS: Record<string, number> = {
  factor: 60,
  technicals: 5,
  analyst: 20,
  earnings: 20,
  news: 3,
  insider: 20,
  options: 5,
  premarket: 1,
  macro: 20,
  calendar: 5,
  political_impact: 5,
  geopolitical_impact: 5,
  supply_chain: 60,
};

export const DEFAULT_HORIZON_DAYS = 5;

export function nativeHorizon(signalName: string): number {
  return SIGNAL_HORIZON_DAYS[signalName] ?? DEFAULT_HORIZON_DAYS;
}
