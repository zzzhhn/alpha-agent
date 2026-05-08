/**
 * BYOK (Bring Your Own Key) localStorage helpers.
 *
 * Stores the user's LLM provider credentials in browser localStorage so
 * each request to /alpha/translate (and other LLM-burning endpoints) can
 * inject them as `X-LLM-*` headers. The platform never sees or stores
 * the key — it transits HTTPS only and is only ever passed to LiteLLM
 * server-side.
 *
 * Threat model:
 *   * XSS exfiltration is the standard residual risk. Mitigated by
 *     dependency pinning + restrictive CSP at the Next.js level.
 *   * Origin scoping: localStorage is per-origin, so the key from a
 *     preview deploy URL won't follow the user to production.
 *   * No persistence past `clearByok()` — Settings page surfaces a
 *     "Remove saved credentials" button.
 */

export type LLMProvider = "openai" | "kimi" | "ollama" | "anthropic";

export interface ByokCredentials {
  provider: LLMProvider;
  apiKey: string;
  baseUrl?: string;
  model?: string;
}

const STORAGE_KEY = "alpha-agent.byok.v1";

/** Provider metadata used by the Settings page UI and as defaults when
 *  the user clears a field. Mirrors `_PROVIDER_DEFAULTS` in the backend
 *  `byok.py` module — keep in sync. */
export const PROVIDER_PRESETS: Record<
  LLMProvider,
  { label: string; defaultBase: string; defaultModel: string; help: string }
> = {
  openai: {
    label: "OpenAI",
    defaultBase: "https://api.openai.com/v1",
    defaultModel: "gpt-4o",
    help: "Get a key at platform.openai.com/api-keys",
  },
  kimi: {
    label: "Kimi For Coding",
    defaultBase: "https://api.kimi.com/coding/v1",
    defaultModel: "kimi-for-coding",
    help: "Get a sk-kimi-* key at platform.moonshot.cn/console/api-keys",
  },
  ollama: {
    label: "Ollama (self-hosted)",
    defaultBase: "http://localhost:11434",
    defaultModel: "gemma4:26b",
    help: "Run your own Ollama server; the API key field is ignored",
  },
  anthropic: {
    label: "Anthropic",
    defaultBase: "https://api.anthropic.com",
    defaultModel: "claude-sonnet-4-5",
    help: "Get an sk-ant-* key at console.anthropic.com",
  },
};

export function loadByok(): ByokCredentials | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ByokCredentials>;
    if (
      !parsed.provider ||
      !parsed.apiKey ||
      !(parsed.provider in PROVIDER_PRESETS)
    ) {
      return null;
    }
    return parsed as ByokCredentials;
  } catch {
    // Malformed JSON — surface as "no key set" rather than throwing
    // through every fetch in the app.
    return null;
  }
}

export function saveByok(creds: ByokCredentials): void {
  if (typeof window === "undefined") return;
  // Trim whitespace before persisting — pasted keys often carry a trailing
  // newline from clipboard managers, which would silently fail server-side.
  const cleaned: ByokCredentials = {
    provider: creds.provider,
    apiKey: creds.apiKey.trim(),
    baseUrl: creds.baseUrl?.trim() || undefined,
    model: creds.model?.trim() || undefined,
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cleaned));
}

export function clearByok(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function hasByok(): boolean {
  return loadByok() !== null;
}

/** Convert stored credentials into the X-LLM-* HTTP headers the backend
 *  `byok.get_llm_client` dependency consumes. Returns an empty object
 *  when nothing is configured so callers can spread it unconditionally. */
export function byokHeaders(): Record<string, string> {
  const c = loadByok();
  if (!c) return {};
  const h: Record<string, string> = {
    "X-LLM-Provider": c.provider,
    "X-LLM-API-Key": c.apiKey,
  };
  if (c.baseUrl) h["X-LLM-Base-URL"] = c.baseUrl;
  if (c.model) h["X-LLM-Model"] = c.model;
  return h;
}
