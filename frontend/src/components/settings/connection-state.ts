import { PROVIDER_PRESETS, type LLMProvider } from "@/lib/byok";
import type { ByokGetResponse, ByokRevision } from "@/lib/api/user";

export function savedConnectionMatches(saved: ByokGetResponse | null, provider: LLMProvider, base: string, model: string): boolean {
  if (!saved || saved.provider !== provider) return false;
  const preset = PROVIDER_PRESETS[provider];
  return (saved.base_url || preset.defaultBase) === base && (saved.model || preset.defaultModel) === model;
}

/** "OpenAI" for api.openai.com; otherwise make clear it is an OpenAI-compatible endpoint on another host. */
export function providerDisplay(provider: string, baseUrl: string | null, zh: boolean): string {
  const preset = PROVIDER_PRESETS[provider as LLMProvider];
  const label = preset?.label ?? provider;
  if (!baseUrl) return label;
  let host = "";
  try { host = new URL(baseUrl).host; } catch { return label; }
  const presetHost = (() => { try { return preset ? new URL(preset.defaultBase).host : ""; } catch { return ""; } })();
  if (!host || host === presetHost) return label;
  return provider === "openai" ? `${zh ? "OpenAI 兼容接口" : "OpenAI-compatible"} · ${host}` : `${label} · ${host}`;
}

const LAST_TEST_KEY = "alpha:settings:last_connection_test";
export const CONNECTION_CHANGE_CHANNEL = "alpha:settings:connection-change";

export type LastConnectionTest = ByokRevision & { readonly at: string; readonly ok: boolean };

export function sameConnectionRevision(
  a: ByokRevision | null | undefined,
  b: ByokRevision | null | undefined,
): boolean {
  return Boolean(a && b && a.userId === b.userId && a.provider === b.provider && a.encryptedAt === b.encryptedAt);
}

export function readLastConnectionTest(scope: ByokRevision | null | undefined): LastConnectionTest | null {
  if (!scope) return null;
  try {
    const raw = typeof window === "undefined" ? null : window.localStorage.getItem(LAST_TEST_KEY);
    const value = raw ? JSON.parse(raw) as Partial<LastConnectionTest> : null;
    if (!value || typeof value.ok !== "boolean" || typeof value.at !== "string"
      || !Number.isFinite(Date.parse(value.at))
      || value.userId !== scope.userId || value.provider !== scope.provider
      || value.encryptedAt !== scope.encryptedAt) return null;
    return { userId: scope.userId, provider: scope.provider, encryptedAt: scope.encryptedAt, at: value.at, ok: value.ok };
  } catch {
    return null;
  }
}

export function writeLastConnectionTest(scope: ByokRevision, ok: boolean): LastConnectionTest {
  const { userId, provider, encryptedAt } = scope;
  const value = { userId, provider, encryptedAt, at: new Date().toISOString(), ok };
  try { window.localStorage.setItem(LAST_TEST_KEY, JSON.stringify(value)); } catch { /* session state still has the receipt */ }
  return value;
}

export function openConnectionChangeChannel(): BroadcastChannel | null {
  try { return new BroadcastChannel(CONNECTION_CHANGE_CHANNEL); } catch { return null; }
}

export function announceConnectionChange(userId: string) {
  const channel = openConnectionChangeChannel();
  if (!channel) return;
  try { channel.postMessage(userId); } catch { /* focus revalidates if tab sharing is unavailable */ }
  finally { channel.close(); }
}

export function connectionTestStatus(
  testState: { readonly kind: string },
  lastTest: Pick<LastConnectionTest, "at" | "ok"> | null,
  zh: boolean,
): { value: string; tone: "positive" | "negative" | "default" } {
  if (testState.kind === "running") return { value: zh ? "测试中" : "Running", tone: "default" };
  if (testState.kind === "ok") return { value: zh ? "通过" : "Passed", tone: "positive" };
  if (testState.kind === "fail") return { value: zh ? "失败" : "Failed", tone: "negative" };
  if (!lastTest) return { value: zh ? "未测试" : "Not tested", tone: "default" };
  const when = new Date(lastTest.at).toLocaleString(zh ? "zh-CN" : "en-US", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  return lastTest.ok
    ? { value: `${zh ? "上次通过" : "Passed"} · ${when}`, tone: "positive" }
    : { value: `${zh ? "上次失败" : "Failed"} · ${when}`, tone: "negative" };
}

