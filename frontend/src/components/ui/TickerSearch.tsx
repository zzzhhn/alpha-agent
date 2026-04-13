"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import clsx from "clsx";
import { searchTicker } from "@/lib/api";
import type { TickerSearchResult } from "@/lib/types";

interface TickerSearchProps {
  readonly label: string;
  readonly value: string;
  readonly onChange: (ticker: string) => void;
  readonly placeholder?: string;
  readonly className?: string;
}

export function TickerSearch({
  label,
  value,
  onChange,
  placeholder = "NVDA",
  className,
}: TickerSearchProps) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<readonly TickerSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearch = useCallback(async (q: string) => {
    if (q.length < 1) {
      setResults([]);
      return;
    }
    setIsLoading(true);
    const res = await searchTicker(q);
    if (res.data) {
      setResults(res.data.results);
    }
    setIsLoading(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value.toUpperCase();
      setQuery(val);
      setIsOpen(true);

      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => handleSearch(val), 200);
    },
    [handleSearch]
  );

  const handleSelect = useCallback(
    (ticker: string) => {
      setQuery(ticker);
      onChange(ticker);
      setIsOpen(false);
    },
    [onChange]
  );

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className={clsx("relative flex flex-col gap-1", className)}>
      <label className="text-[11px] text-muted">{label}</label>
      <input
        type="text"
        value={query}
        onChange={handleInputChange}
        onFocus={() => { if (results.length > 0) setIsOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            onChange(query);
            setIsOpen(false);
          }
        }}
        placeholder={placeholder}
        className="rounded-lg border border-border bg-card px-3 py-2 font-mono text-sm text-text placeholder:text-muted/50 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
      />

      {isOpen && results.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-lg border border-border bg-card shadow-xl">
          {results.map((r) => (
            <button
              key={r.ticker}
              type="button"
              onClick={() => handleSelect(r.ticker)}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-white/5"
            >
              <span className="font-mono font-bold text-accent">
                {r.ticker}
              </span>
              <span className="truncate text-muted">{r.name}</span>
              <span className="ml-auto text-[10px] text-muted">
                {r.sector}
              </span>
            </button>
          ))}
        </div>
      )}

      {isOpen && isLoading && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted">
          Searching...
        </div>
      )}
    </div>
  );
}
