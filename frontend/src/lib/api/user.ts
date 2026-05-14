// frontend/src/lib/api/user.ts
//
// Typed client for the Phase 4 /api/user/* backend routes. All calls use
// credentials: "include" so the same-origin NextAuth JWT cookie rides
// along; the Next.js rewrite forwards it to FastAPI as the Bearer token.
//
// API_BASE mirrors the pattern in ./client.ts (same env var, same fallback).
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app";

export interface ByokGetResponse {
  provider: string;
  last4: string;
  model: string | null;
  base_url: string | null;
  encrypted_at: string;
  last_used_at: string | null;
}

export interface ByokSaveResponse {
  provider: string;
  last4: string;
  encrypted_at: string;
}

export async function getByok(): Promise<ByokGetResponse | null> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    credentials: "include",
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getByok failed: HTTP ${r.status}`);
  return (await r.json()) as ByokGetResponse;
}

export async function saveByok(body: {
  provider: string;
  api_key: string;
  model?: string;
  base_url?: string;
}): Promise<ByokSaveResponse> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`saveByok failed: HTTP ${r.status}`);
  return (await r.json()) as ByokSaveResponse;
}

export async function deleteByok(): Promise<void> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) throw new Error(`deleteByok failed: HTTP ${r.status}`);
}

export async function deleteAccount(): Promise<void> {
  const r = await fetch(`${API_BASE}/api/user/account/delete`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) throw new Error(`deleteAccount failed: HTTP ${r.status}`);
}

export async function exportAccount(): Promise<Record<string, unknown>> {
  const r = await fetch(`${API_BASE}/api/user/account/export`, {
    credentials: "include",
  });
  if (!r.ok) throw new Error(`exportAccount failed: HTTP ${r.status}`);
  return (await r.json()) as Record<string, unknown>;
}
