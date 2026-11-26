// frontend/src/lib/api/user.ts
//
// Typed client for the Phase 4 /api/user/* backend routes. All calls use
// credentials: "include" so the same-origin NextAuth JWT cookie rides
// along; the Next.js rewrite forwards it to FastAPI as the Bearer token.
//
// Browser: same-origin "" so /api/* goes through the Next.js middleware
// (which injects the auth Bearer header) and the next.config.mjs rewrite.
// Server (SSR): the absolute backend URL, since middleware does not run on
// server-component fetches. Auth-gated endpoints are only called client-side.
const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app"
    : "";

export interface ByokRevision {
  readonly userId: string;
  readonly provider: string;
  readonly encryptedAt: string;
}

const BYOK_ACCOUNT = "X-BYOK-Account";
const BYOK_PROVIDER = "X-BYOK-Provider";
const BYOK_REVISION = "X-BYOK-Revision";

function responseRevision(headers: Headers): ByokRevision | null {
  const userId = headers.get(BYOK_ACCOUNT);
  const provider = headers.get(BYOK_PROVIDER);
  const encryptedAt = headers.get(BYOK_REVISION);
  return userId && provider && encryptedAt ? { userId, provider, encryptedAt } : null;
}

export class ByokProbeError extends Error {
  constructor(message: string, readonly scope: ByokRevision | null) {
    super(message);
  }
}

export interface ByokGetResponse {
  provider: string;
  last4: string;
  model: string | null;
  base_url: string | null;
  encrypted_at: string;
  last_used_at: string | null;
  scope?: ByokRevision | null;
}

export interface ByokSaveResponse {
  provider: string;
  last4: string;
  encrypted_at: string;
  scope: ByokRevision | null;
}

export interface ByokTestResponse {
  provider: string;
  model: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  scope: ByokRevision | null;
}

export async function getByok(): Promise<ByokGetResponse | null> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    credentials: "include",
    cache: "no-store",
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getByok failed: HTTP ${r.status}`);
  return { ...(await r.json()), scope: responseRevision(r.headers) } as ByokGetResponse;
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
  if (!r.ok) {
    // Surface the backend's detail (e.g. "server master key is misconfigured:
    // master key must decode to 32 bytes"), not just the status code — an
    // opaque "HTTP 400" hides the actual, fixable reason.
    const detail = await r
      .json()
      .then((b) => (b as { detail?: string })?.detail)
      .catch(() => undefined);
    throw new Error(
      detail ? `saveByok failed: ${detail}` : `saveByok failed: HTTP ${r.status}`,
    );
  }
  return { ...(await r.json()), scope: responseRevision(r.headers) } as ByokSaveResponse;
}

export async function testByok(scope?: ByokRevision): Promise<ByokTestResponse> {
  const r = await fetch(`${API_BASE}/api/user/byok/test`, {
    method: "POST",
    headers: scope ? {
      [BYOK_ACCOUNT]: scope.userId,
      [BYOK_PROVIDER]: scope.provider,
      [BYOK_REVISION]: scope.encryptedAt,
    } : undefined,
    credentials: "include",
  });
  if (!r.ok) {
    const detail = await r
      .json()
      .then((b) => (b as { detail?: string })?.detail)
      .catch(() => undefined);
    throw new ByokProbeError(detail ?? `LLM connection test failed: HTTP ${r.status}`, responseRevision(r.headers));
  }
  return { ...(await r.json()), scope: responseRevision(r.headers) } as ByokTestResponse;
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
