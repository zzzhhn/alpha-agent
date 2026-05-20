"use client";

// Resolves whether the signed-in user has a server-side BYOK LLM key
// configured (the canonical store is /api/user/byok / the user_byok table;
// the localStorage byok.ts path is legacy). Used to show a lock affordance
// on LLM-gated surfaces (Personas, Rich Brief) BEFORE the user clicks and
// hits an error.
//
// Gated on the auth session so an unauthenticated visitor never fires the
// auth-only endpoint (which would 401-spam the console each page load).

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { getByok } from "@/lib/api/user";

export function useHasByok(): {
  hasKey: boolean;
  loading: boolean;
  authed: boolean;
} {
  const { status } = useSession();
  const [hasKey, setHasKey] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated") {
      setHasKey(false);
      setLoading(status === "loading");
      return;
    }
    let cancelled = false;
    setLoading(true);
    getByok()
      .then((r) => {
        if (!cancelled) setHasKey(Boolean(r && r.provider));
      })
      .catch(() => {
        if (!cancelled) setHasKey(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  return { hasKey, loading, authed: status === "authenticated" };
}
