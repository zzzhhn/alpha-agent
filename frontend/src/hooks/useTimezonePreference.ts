"use client";

import { useEffect, useState } from "react";
export type TimezonePreference = "local" | "Asia/Shanghai" | "America/New_York" | "UTC";
export const TIMEZONE_KEY = "alpha:display_timezone";
const valid = (value: string | null): value is TimezonePreference =>
  ["local", "Asia/Shanghai", "America/New_York", "UTC"].includes(value ?? "");

export function useTimezonePreference() {
  // Deterministic UTC output for SSR + initial hydration, then explicit local.
  const [preference, setPreference] = useState<TimezonePreference>("local");
  const [localZone, setLocalZone] = useState("UTC");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setLocalZone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
    try { const saved = localStorage.getItem(TIMEZONE_KEY); if (valid(saved)) setPreference(saved); } catch { /* storage may be disabled */ }
    setReady(true);
    const sync = (event: StorageEvent) => { if (event.key === TIMEZONE_KEY && valid(event.newValue)) setPreference(event.newValue); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  const choose = (value: string) => {
    if (!valid(value)) return;
    setPreference(value);
    try { localStorage.setItem(TIMEZONE_KEY, value); } catch { /* preference still works in memory */ }
    window.dispatchEvent(new StorageEvent("storage", { key: TIMEZONE_KEY, newValue: value }));
  };
  return { preference, choose, localZone, ready, timeZone: ready ? (preference === "local" ? localZone : preference) : "UTC" };
}
