import { PROVIDER_PRESETS, type LLMProvider } from "@/lib/byok";
import type { ByokGetResponse } from "@/lib/api/user";

export function savedConnectionMatches(saved: ByokGetResponse | null, provider: LLMProvider, base: string, model: string): boolean {
  if (!saved || saved.provider !== provider) return false;
  const preset = PROVIDER_PRESETS[provider];
  return (saved.base_url || preset.defaultBase) === base && (saved.model || preset.defaultModel) === model;
}
