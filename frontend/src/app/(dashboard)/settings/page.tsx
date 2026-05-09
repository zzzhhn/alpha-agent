"use client";

/**
 * Settings page — BYOK credential management.
 *
 * Phase 2 (BYOK): the open-source deploy of alpha-agent doesn't supply
 * an LLM key on the public endpoint. Visitors paste their own provider
 * credentials here; values live in browser localStorage and ship as
 * X-LLM-* headers on every request via `lib/byok.ts`.
 *
 * Stage 3 (redesign): visual layer ported to the workstation aesthetic
 * via the `tm/*` primitive set. ALL business logic (state shape,
 * effects, save/test/clear handlers, error parsing, request payload)
 * is unchanged from the previous version. The diff is purely
 * className + container components.
 *
 * UX goals (unchanged):
 *   * Clear what's stored where (localStorage, never on our server)
 *   * One-click test against the configured provider before saving
 *   * Easy clear / reset
 *   * Sane provider-aware defaults so most users only need to paste a key
 */

import { useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton } from "@/components/tm/TmButton";
import {
  TmFieldShell,
  TmInput,
  TmSelect,
} from "@/components/tm/TmField";
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
          // The translate endpoint enforces budget_tokens ∈ [500, 8000];
          // 256 here would 422-fail BEFORE reaching the BYOK header check
          // and look like a credential bug. Send the minimum 500 so the
          // probe is the cheapest valid request.
          text: "5-day mean reversion",
          universe: "SP500",
          budget_tokens: 500,
        }),
      });
      const elapsed = Math.round(performance.now() - started);
      if (!res.ok) {
        const body = await res.text();
        let detail = body.slice(0, 240);
        try {
          const parsed = JSON.parse(body) as { detail?: unknown };
          if (parsed?.detail !== undefined) {
            // FastAPI 422 returns detail as an array of validation errors
            // like [{ type, loc: ["body","budget_tokens"], msg, ... }].
            // Render those readably ("body.budget_tokens: msg") instead
            // of dumping the raw JSON, which made past 422s look like
            // a BYOK credential issue.
            if (Array.isArray(parsed.detail)) {
              detail = parsed.detail
                .map((e: unknown) => {
                  if (typeof e === "object" && e !== null) {
                    const err = e as { loc?: unknown[]; msg?: string };
                    const path = (err.loc ?? []).join(".");
                    return `${path}: ${err.msg ?? "validation error"}`;
                  }
                  return String(e);
                })
                .join("; ")
                .slice(0, 240);
            } else if (typeof parsed.detail === "string") {
              detail = parsed.detail;
            } else {
              detail = JSON.stringify(parsed.detail).slice(0, 240);
            }
          }
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
    <div className="mx-auto flex max-w-3xl flex-col gap-4 font-tm-mono">
      {/* Page header pane — terminal aesthetic title row replaces the
          large h1 + lede paragraph from the legacy version. */}
      <TmPane
        title="SETTINGS / BYOK"
        meta={zh ? "本地凭证 · 仅浏览器存储" : "local credentials · browser-only"}
      >
        <p className="px-3 py-2.5 text-[11.5px] leading-relaxed text-tm-fg-2">
          {zh
            ? "你的 API key 只保存在本浏览器的 localStorage，每次请求作为 header 发送给后端用于调用大模型。alpha-agent 服务器从不存储或日志记录你的 key。"
            : "Your API key is stored in this browser's localStorage and sent as a request header on each LLM call. The alpha-agent server never stores or logs your key."}
        </p>
      </TmPane>

      {/* Credentials form pane */}
      <TmPane title="CREDENTIALS" meta={preset.help}>
        <div className="flex flex-col gap-3 px-3 py-3">
          <TmSelect
            label={zh ? "服务商 / PROVIDER" : "PROVIDER"}
            value={provider}
            onChange={(v) => {
              setProvider(v as LLMProvider);
              // Clear test result so a stale "OK" doesn't carry over to a
              // different provider's draft credentials.
              setTestState({ kind: "idle" });
            }}
            options={PROVIDER_OPTIONS}
          />

          {/* API key field — bypass the standard text input because we
              need <input type="password"> for native masking that doesn't
              interfere with editing. The reveal toggle sits below the
              input as an inline secondary control. */}
          <TmFieldShell label={zh ? "API KEY" : "API KEY"}>
            <input
              type={revealKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                provider === "ollama"
                  ? zh ? "Ollama 不需要 key（任意填写）" : "Not required for Ollama"
                  : "sk-..."
              }
              className="h-8 w-full border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[12px] text-tm-fg outline-none transition-colors placeholder:text-tm-muted focus:border-tm-accent"
            />
            <button
              type="button"
              onClick={() => setRevealKey((r) => !r)}
              className="self-start text-[10.5px] uppercase tracking-[0.06em] text-tm-info hover:text-tm-fg"
            >
              {revealKey
                ? zh ? "隐藏" : "HIDE"
                : zh ? "显示" : "REVEAL"}
            </button>
          </TmFieldShell>

          <TmInput
            label={zh ? "BASE URL（可选，留空用默认）" : "BASE URL (optional)"}
            value={baseUrl}
            onChange={setBaseUrl}
            placeholder={preset.defaultBase}
          />
          <TmInput
            label={zh ? "MODEL ID（可选）" : "MODEL ID (optional)"}
            value={model}
            onChange={setModel}
            placeholder={preset.defaultModel}
          />

          {/* Effective-config readout — terminal-style code block. */}
          <div className="border border-tm-rule bg-tm-bg-3 px-3 py-2 text-[10.5px] text-tm-muted">
            <div className="uppercase tracking-[0.06em]">
              {zh ? "实际请求将使用：" : "REQUEST WILL USE"}
            </div>
            <code className="mt-1 block break-all text-tm-fg-2">
              {provider} · {effectiveBase} · {effectiveModel}
            </code>
          </div>

          <div className="flex flex-wrap gap-2">
            <TmButton variant="primary" onClick={handleSave} disabled={!canSave}>
              {zh ? "保存" : "SAVE"}
            </TmButton>
            <TmButton
              variant="secondary"
              onClick={handleTest}
              disabled={!canSave || testState.kind === "running"}
            >
              {testState.kind === "running"
                ? zh ? "测试中…" : "TESTING…"
                : zh ? "测试连通" : "TEST CONNECTION"}
            </TmButton>
            <TmButton variant="ghost" onClick={handleClear}>
              {zh ? "清除已保存" : "CLEAR SAVED"}
            </TmButton>
          </div>

          {savedAt && (
            <p className="text-[10.5px] uppercase tracking-[0.06em] text-tm-pos">
              {zh ? `已保存于 ${savedAt}` : `SAVED AT ${savedAt}`}
            </p>
          )}

          {testState.kind === "ok" && (
            <p className="text-[10.5px] uppercase tracking-[0.04em] text-tm-pos">
              {zh
                ? `✓ 连通正常（${testState.ms}ms，prompt ${testState.tokens.prompt} / completion ${testState.tokens.completion} tokens）`
                : `✓ CONNECTED · ${testState.ms}ms · ${testState.tokens.prompt} prompt / ${testState.tokens.completion} completion tokens`}
            </p>
          )}
          {testState.kind === "fail" && (
            <p className="text-[10.5px] text-tm-neg">
              {zh ? "✗ 失败：" : "✗ FAILED: "}
              {testState.status ? `HTTP ${testState.status} · ` : ""}
              {testState.message}
            </p>
          )}
        </div>
      </TmPane>

      {/* Footnotes pane — origin-scoping warnings. */}
      <TmPane title="NOTES" meta={zh ? "凭证存储说明" : "credential storage"}>
        <div className="flex flex-col gap-1.5 px-3 py-2.5 text-[10.5px] leading-relaxed text-tm-muted">
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
      </TmPane>
    </div>
  );
}
