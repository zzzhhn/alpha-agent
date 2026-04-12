"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface UsePollingOptions<T> {
  readonly fetcher: () => Promise<T>;
  readonly intervalMs?: number;
  readonly enabled?: boolean;
}

interface UsePollingResult<T> {
  readonly data: T | null;
  readonly error: string | null;
  readonly isLoading: boolean;
  readonly lastUpdated: string | null;
  readonly refetch: () => Promise<void>;
}

export function usePolling<T>({
  fetcher,
  intervalMs = 30_000,
  enabled = true,
}: UsePollingOptions<T>): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null
  );
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unknown error";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    refetch();

    intervalRef.current = setInterval(refetch, intervalMs);

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
      }
    };
  }, [enabled, intervalMs, refetch]);

  return { data, error, isLoading, lastUpdated, refetch };
}
