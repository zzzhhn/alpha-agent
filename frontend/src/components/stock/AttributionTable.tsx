"use client";

import { useState, useMemo } from "react";
import clsx from "clsx";
import type { RatingCard } from "@/lib/api/picks";

type SortKey = "signal" | "z" | "weight" | "contribution";

export default function AttributionTable({ card }: { card: RatingCard }) {
  const [sortKey, setSortKey] = useState<SortKey>("contribution");
  const [desc, setDesc] = useState(true);

  const sorted = useMemo(() => {
    const out = [...card.breakdown];
    out.sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortKey];
      const bv = (b as Record<string, unknown>)[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return desc ? bv - av : av - bv;
      }
      return desc
        ? String(bv).localeCompare(String(av))
        : String(av).localeCompare(String(bv));
    });
    return out;
  }, [card.breakdown, sortKey, desc]);

  const setSort = (k: SortKey) => {
    if (sortKey === k) {
      setDesc((d) => !d);
    } else {
      setSortKey(k);
      setDesc(true);
    }
  };

  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr className="text-zinc-400 border-b border-zinc-800">
          <SortTh
            onClick={() => setSort("signal")}
            active={sortKey === "signal"}
            desc={desc}
          >
            signal
          </SortTh>
          <SortTh
            onClick={() => setSort("z")}
            active={sortKey === "z"}
            desc={desc}
            numeric
          >
            z
          </SortTh>
          <SortTh
            onClick={() => setSort("weight")}
            active={sortKey === "weight"}
            desc={desc}
            numeric
          >
            w
          </SortTh>
          <SortTh
            onClick={() => setSort("contribution")}
            active={sortKey === "contribution"}
            desc={desc}
            numeric
          >
            contrib
          </SortTh>
          <th className="px-2 py-1.5 text-left">source</th>
          <th className="px-2 py-1.5 text-left">time</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((b) => (
          <tr
            key={b.signal}
            className={clsx(
              "border-b border-zinc-900",
              b.contribution === 0 ? "opacity-40" : "",
            )}
          >
            <td className="px-2 py-1">{b.signal}</td>
            <td className="px-2 py-1 text-right font-mono">
              {b.z >= 0 ? "+" : ""}
              {b.z.toFixed(2)}
            </td>
            <td className="px-2 py-1 text-right font-mono">
              {b.weight.toFixed(2)}
            </td>
            <td
              className={clsx(
                "px-2 py-1 text-right font-mono",
                b.contribution > 0
                  ? "text-emerald-300"
                  : b.contribution < 0
                    ? "text-rose-300"
                    : "",
              )}
            >
              {b.contribution >= 0 ? "+" : ""}
              {b.contribution.toFixed(2)}
            </td>
            <td className="px-2 py-1 text-zinc-500">{b.source}</td>
            <td className="px-2 py-1 text-zinc-500">
              {new Date(b.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SortTh({
  children,
  onClick,
  active,
  desc,
  numeric,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active: boolean;
  desc: boolean;
  numeric?: boolean;
}) {
  return (
    <th
      onClick={onClick}
      className={clsx(
        "cursor-pointer px-2 py-1.5 select-none",
        numeric ? "text-right" : "text-left",
        active ? "text-zinc-200" : "",
      )}
    >
      {children}
      {active ? (desc ? " ▼" : " ▲") : ""}
    </th>
  );
}
