"use client";

/**
 * Settings page — BYOK credential management.
 *
 * Phase 2 (BYOK): the open-source deploy of alpha-agent doesn't supply
 * an LLM key on the public endpoint. Visitors paste their own provider
 * credentials here; values live in browser localStorage and ship as
 * X-LLM-* headers on every request via `lib/byok.ts`.
 *
 * UX goals:
 *   * Clear what's stored where (localStorage, never on our server)
 *   * One-click test against the configured provider before saving
 *   * Easy clear / reset
 *   * Sane provider-aware defaults so most users only need to paste a key
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  type ByokCredentials,
  type LLMProvider,
  PROVIDER_PRESETS,
  clearByok,
  loadByok,
  saveByok,
} from "@/lib/byok";

type TestState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; ms: number; tokens: { prompt: number; completion: number } }
  | { kind: "fail"; status: number | null; message: string };

const PROVIDER_OPTIONS = [
  { value: "openai", label: PROVIDER_PRESETS.openai.label },
  { value: "kimi", label: PROVIDER_PRESETS.kimi.label },
  { value: "ollama", label: PROVIDER_PRESETS.ollama.label },
  { value: "anthropic", label: PROVIDER_PRESETS.anthropic.label },
];

export default function SettingsPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";

  const [provider, setProvider] = useState<LLMProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [revealKey, setRevealKey] = useState(false);
  const [testState, setTestState] = useState<TestState>({ kind: "idle" });
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // Hydrate from localStorage on mount.
  useEffect(() => {
    const c = loadByok();
    if (!c) return;
    setProvider(c.provider);
    setApiKey(c.apiKey);
    setBaseUrl(c.baseUrl ?? "");
    setModel(c.model ?? "");
  }, []);

  const preset = PROVIDER_PRESETS[provider];
  const effectiveBase = baseUrl.trim() || preset.defaultBase;
  const effectiveModel = model.trim() || preset.defaultModel;
  const canSave = apiKey.trim().length > 4;

  function handleSave() {
    const creds: ByokCredentials = {
      provider,
      apiKey,
      baseUrl: baseUrl.trim() || undefined,
      model: model.trim() || undefined,
    };
    saveByok(creds);
    setSavedAt(new Date().toLocaleTimeString());
  }

  function handleClear() {
    clearByok();
    setProvider("openai");
    setApiKey("");
    setBaseUrl("");
    setModel("");
    setSavedAt(null);
    setTestState({ kind: "idle" });
  }

  // Live test — fires the actual /alpha/translate endpoint with the
  // user's current draft credentials. We craft the headers manually
  // from local form state (NOT from `byokHeaders()`) so the user can
  // test BEFORE saving — useful for catching typos before persisting.
  async function handleTest() {
    if (!canSave) return;
    setTestState({ kind: "running" });
    const started = performance.now();
    const apiBase =
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6008";
    try {
      const res = await fetch(`${apiBase}/api/v1/alpha/translate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-LLM-Provider": provider,
          "X-LLM-API-Key": apiKey.trim(),
          ...(baseUrl.trim() ? { "X-LLM-Base-URL": baseUrl.trim() } : {}),
          ...(model.trim() ? { "X-LLM-Model": model.trim() } : {}),
        },
        body: JSON.stringify({
          text: "5-day mean reversion",
          universe: "SP500",
          budget_tokens: 256,
        }),
      });
      const elapsed = Math.round(performance.now() - started);
      if (!res.ok) {
        const body = await res.text();
        let detail = body.slice(0, 240);
        try {
          const parsed = JSON.parse(body) as { detail?: unknown };
          if (parsed?.detail) detail = JSON.stringify(parsed.detail).slice(0, 240);
        } catch {
          // body is not JSON — keep raw slice
        }
        setTestState({ kind: "fail", status: res.status, message: detail });
        return;
      }
      const data = (await res.json()) as {
        token_usage?: { prompt_tokens?: number; completion_tokens?: number };
      };
      const usage = data.token_usage ?? {};
      setTestState({
        kind: "ok",
        ms: elapsed,
        tokens: {
          prompt: usage.prompt_tokens ?? 0,
          completion: usage.completion_tokens ?? 0,
        },
      });
    } catch (exc) {
      setTestState({
        kind: "fail",
        status: null,
        message: exc instanceof Error ? exc.message : String(exc),
      });
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-[var(--text)]">
          {zh ? "LLM 凭证（BYOK）" : "LLM Credentials (BYOK)"}
        </h1>
        <p className="text-sm text-[var(--muted)]">
          {zh
            ? "你的 API key 只保存在本浏览器的 localStorage，每次请求作为 header 发送给后端用于调用大模型。alpha-agent 服务器从不存储或日志记录你的 key。"
            : "Your API key is stored in this browser's localStorage and sent as a request header on each LLM call. The alpha-agent server never stores or logs your key."}
        </p>
      </header>

      <div className="flex flex-col gap-4 rounded-lg border border-[var(--border)] bg-[var(--card)] p-5">
        <Select
          label={zh ? "服务商" : "Provider"}
          value={provider}
          onChange={(v) => {
            setProvider(v as LLMProvider);
            // Clear test result so a stale "OK" doesn't carry over to a
            // different provider's draft credentials.
            setTestState({ kind: "idle" });
          }}
          options={PROVIDER_OPTIONS}
        />
        <p className="-mt-2 text-xs text-[var(--muted)]">{preset.help}</p>

        {/* API key field — bypass the shared Input component because we
            need <input type="password"> for native masking that doesn't
            interfere with editing (a value-replacement mask, like the
            previous version, makes typing into a non-revealed field
            confusing). */}
        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-muted">API Key</label>
          <input
            type={revealKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              provider === "ollama"
                ? zh ? "Ollama 不需要 key（任意填写）" : "Not required for Ollama"
                : "sk-..."
            }
            className="rounded-md border border-[var(--border)] bg-[var(--bg-2)] px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]"
          />
          <button
            type="button"
            onClick={() => setRevealKey((r) => !r)}
            className="self-start text-xs text-[var(--accent)] hover:underline"
          >
            {revealKey
              ? zh ? "隐藏" : "Hide"
              : zh ? "显示" : "Reveal"}
          </button>
        </div>

        <Input
          label={zh ? "Base URL（可选，留空用默认）" : "Base URL (optional)"}
          value={baseUrl}
          onChange={setBaseUrl}
          placeholder={preset.defaultBase}
        />
        <Input
          label={zh ? "模型 ID（可选）" : "Model ID (optional)"}
          value={model}
          onChange={setModel}
          placeholder={preset.defaultModel}
        />

        <div className="rounded-md border border-[var(--border)] bg-[var(--bg-2)] p-3 text-xs text-[var(--muted)]">
          <div>
            {zh ? "实际请求将使用：" : "The request will use:"}
          </div>
          <code className="mt-1 block break-all text-[var(--text-secondary)]">
            {provider} · {effectiveBase} · {effectiveModel}
          </code>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={handleSave} disabled={!canSave}>
            {zh ? "保存" : "Save"}
          </Button>
          <Button variant="secondary" onClick={handleTest} disabled={!canSave || testState.kind === "running"}>
            {testState.kind === "running"
              ? zh ? "测试中…" : "Testing…"
              : zh ? "测试连通" : "Test connection"}
          </Button>
          <Button variant="ghost" onClick={handleClear}>
            {zh ? "清除已保存" : "Clear saved"}
          </Button>
        </div>

        {savedAt && (
          <p className="text-xs text-[var(--green)]">
            {zh ? `已保存于 ${savedAt}` : `Saved at ${savedAt}`}
          </p>
        )}

        {testState.kind === "ok" && (
          <p className="text-xs text-[var(--green)]">
            {zh
              ? `✓ 连通正常（${testState.ms}ms，prompt ${testState.tokens.prompt} tokens / completion ${testState.tokens.completion} tokens）`
              : `✓ Connected (${testState.ms}ms, ${testState.tokens.prompt} prompt / ${testState.tokens.completion} completion tokens)`}
          </p>
        )}
        {testState.kind === "fail" && (
          <p className="text-xs text-[var(--red)]">
            {zh ? "✗ 失败：" : "✗ Failed: "}
            {testState.status ? `HTTP ${testState.status} · ` : ""}
            {testState.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 text-xs text-[var(--muted)]">
        <p>
          {zh
            ? "提示：localStorage 仅在本浏览器、本域名下可见。换浏览器或换设备需要重新填写。"
            : "Note: localStorage is scoped to this browser and origin. You'll need to re-enter on a different browser or device."}
        </p>
        <p>
          {zh
            ? "提示：preview 部署 URL 与 production 是不同 origin，凭证不会跨越。"
            : "Note: Vercel preview URLs and production are separate origins; credentials won't carry across."}
        </p>
      </div>
    </div>
  );
}

