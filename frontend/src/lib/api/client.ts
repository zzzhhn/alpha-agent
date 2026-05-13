// frontend/src/lib/api/client.ts
import type { paths } from "../../../api-types.gen";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app";

type ApiError = { code: string; message: string; retry_after_sec?: number };

export class ApiException extends Error {
  constructor(public status: number, public body: ApiError) {
    super(body.message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    headers: { "content-type": "application/json" },
    cache: "no-store",
  });
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as ApiError;
    throw new ApiException(r.status, body);
  }
  return (await r.json()) as T;
}

export async function apiPost<T, B>(path: string, body: B): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const errBody = (await r.json().catch(() => ({}))) as ApiError;
    throw new ApiException(r.status, errBody);
  }
  return (await r.json()) as T;
}

// Re-export paths type so consumers can reference openapi route shapes if needed
export type { paths };
