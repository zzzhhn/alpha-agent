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
  const generation = useRef(0);
  const inFlight = useRef<Promise<void> | null>(null);
  fetcherRef.current = fetcher;

  const refetch = useCallback(() => {
    if (inFlight.current) return inFlight.current;
    const current = generation.current;
    const request = (async () => {
      try {
        setIsLoading(true);
        const result = await fetcherRef.current();
        if (current !== generation.current) return;
        setData(result);
        setError(null);
        setLastUpdated(new Date().toISOString());
      } catch (err) {
        if (current === generation.current) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (current === generation.current) setIsLoading(false);
      }
    })();
    inFlight.current = request;
    void request.finally(() => {
      if (inFlight.current === request) inFlight.current = null;
    });
    return request;
  }, []);

  useEffect(() => {
    if (!enabled) { setIsLoading(false); return; }

    const pollVisible = () => {
      if (document.visibilityState === "visible") void refetch();
    };
    pollVisible();
    document.addEventListener("visibilitychange", pollVisible);

    intervalRef.current = setInterval(pollVisible, intervalMs);

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
      }
      generation.current += 1;
      inFlight.current = null;
      document.removeEventListener("visibilitychange", pollVisible);
    };
  }, [enabled, intervalMs, refetch]);

  return { data, error, isLoading, lastUpdated, refetch };
}
