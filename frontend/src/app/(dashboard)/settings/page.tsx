"use client";

/**
 * Settings page — BYOK credential management.
 *
 * Phase 2 (BYOK): the open-source deploy of alpha-agent doesn't supply
 * an LLM key on the public endpoint. Visitors paste their own provider
 * credentials here; values live in browser localStorage and ship as
 * X-LLM-* headers on every request via `lib/byok.ts`.
 *
 * Stage 3 redesign — re-port to match the design's actual workstation
 * layout (full-width edge-to-edge `tm-screen` with stacked panes
 * separated by hairlines, NOT centred rounded cards). Form fields use
 * the `tm-form` flat label-stacked pattern; actions sit in a hairline
 * `tm-form-foot` bar at the bottom of the credentials pane. ALL
 * business logic preserved verbatim.
 */

import { useEffect, useState } from "react";
import { signOut } from "next-auth/react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmButton } from "@/components/tm/TmButton";
import {
  type ByokCredentials,
  type LLMProvider,
  PROVIDER_PRESETS,
  clearByok,
  hasByok,
  loadByok,
  saveByok as saveByokLocal,
} from "@/lib/byok";
import {
  getByok,
  saveByok as saveByokServer,
  deleteAccount,
  exportAccount,
} from "@/lib/api/user";
import { t } from "@/lib/i18n";
import WeightsEditor from "@/components/settings/WeightsEditor";
import WatchlistEditor from "@/components/settings/WatchlistEditor";

type TestState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; ms: number; tokens: { prompt: number; completion: number } }
  | { kind: "fail"; status: number | null; message: string };

const PROVIDER_VALUES: ReadonlyArray<LLMProvider> = ["openai", "kimi", "ollama", "anthropic"];

// Workstation form-row label class (mirrors `.tm-form label`).
const FORM_LABEL =
  "block text-[10.5px] font-semibold uppercase tracking-[0.06em] text-tm-muted";

const FORM_INPUT =
  "h-7 w-full bg-tm-bg-2 border border-tm-rule px-2 font-tm-mono text-[11.5px] text-tm-fg outline-none transition-colors placeholder:text-tm-muted focus:border-tm-accent";

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
  // Server-side BYOK state
  const [serverLast4, setServerLast4] = useState<string | null>(null);
  // Import banner: shown when localStorage has a key but server does not
  const [showImportBanner, setShowImportBanner] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  // Danger zone
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteInProgress, setDeleteInProgress] = useState(false);
  const [exportInProgress, setExportInProgress] = useState(false);

  useEffect(() => {
    const c = loadByok();
    if (!c) return;
    setProvider(c.provider);
    setApiKey(c.apiKey);
    setBaseUrl(c.baseUrl ?? "");
    setModel(c.model ?? "");
  }, []);

  // On mount: fetch server-side BYOK status and decide whether to show
  // the import banner (localStorage has a key but server has none).
  useEffect(() => {
    getByok()
      .then((resp) => {
        if (resp) {
          setServerLast4(resp.last4);
        } else {
          // Server has no key - show import banner if localStorage does.
          const local = loadByok();
          if (local) setShowImportBanner(true);
        }
      })
      .catch(() => {
        // Silently swallow network errors - import banner stays hidden.
      });
  }, []);

  const preset = PROVIDER_PRESETS[provider];
  const effectiveBase = baseUrl.trim() || preset.defaultBase;
  const effectiveModel = model.trim() || preset.defaultModel;
  const canSave = apiKey.trim().length > 4;

  async function handleSave() {
    // POST to server-side AES-256-GCM storage. Plaintext key is used
    // only inside this call and not persisted to component state.
    try {
      const resp = await saveByokServer({
        provider,
        api_key: apiKey.trim(),
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      setServerLast4(resp.last4);
      setSavedAt(new Date().toLocaleTimeString());
      // Also keep localStorage in sync so byokHeaders() still works for
      // existing code paths that read X-LLM-* headers from it.
      saveByokLocal({
        provider,
        apiKey,
        baseUrl: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      } satisfies ByokCredentials);
    } catch (err) {
      setSavedAt(null);
      setTestState({
        kind: "fail",
        status: null,
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }

  async function handleImport() {
    const local = loadByok();
    if (!local) {
      setShowImportBanner(false);
      return;
    }
    setImportBusy(true);
    try {
      const resp = await saveByokServer({
        provider: local.provider,
        api_key: local.apiKey,
        base_url: local.baseUrl,
        model: local.model,
      });
      setServerLast4(resp.last4);
      clearByok();
      setShowImportBanner(false);
    } catch {
      // On error leave banner visible so user can retry.
    } finally {
      setImportBusy(false);
    }
  }

  function handleDiscardImport() {
    clearByok();
    setShowImportBanner(false);
  }

  async function handleExport() {
    setExportInProgress(true);
    try {
      const data = await exportAccount();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "alpha-agent-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Errors are non-critical; user can retry.
    } finally {
      setExportInProgress(false);
    }
  }

  async function handleDeleteAccount() {
    if (deleteConfirm !== "DELETE") return;
    setDeleteInProgress(true);
    try {
      await deleteAccount();
      await signOut({ callbackUrl: "/signin" });
    } catch {
      setDeleteInProgress(false);
    }
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
          // budget_tokens enforced ≥ 500 by FastAPI; smaller would 422
          // before the BYOK header check fires.
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
            // FastAPI 422 ⇒ array of validation errors. Render readably.
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
    <TmScreen>
      {showImportBanner && (
        <div className="flex items-center gap-3 border-b border-tm-rule bg-tm-accent-soft px-4 py-2 font-tm-mono text-[11px] text-tm-fg">
          <span className="flex-1">
            {t(locale, "settings.byok.import_banner")}
          </span>
          <button
            type="button"
            disabled={importBusy}
            onClick={() => { void handleImport(); }}
            className="border border-tm-accent bg-tm-accent px-3 py-0.5 text-[10.5px] uppercase tracking-[0.06em] text-white disabled:opacity-50"
          >
            {t(locale, "settings.byok.import_button")}
          </button>
          <button
            type="button"
            disabled={importBusy}
            onClick={handleDiscardImport}
            className="border border-tm-rule px-3 py-0.5 text-[10.5px] uppercase tracking-[0.06em] text-tm-fg-2 hover:text-tm-fg disabled:opacity-50"
          >
            {t(locale, "settings.byok.discard_button")}
          </button>
        </div>
      )}
      <TmSubbar>
        <TmSubbarKV
          label={zh ? "存储" : "STORAGE"}
          value={serverLast4 ? `server · …${serverLast4}` : "server · none"}
        />
        <TmSubbarSep />
        <TmSubbarKV label={zh ? "服务商" : "PROVIDER"} value={provider} />
        <TmSubbarSep />
        <TmSubbarKV label="MODEL" value={effectiveModel} />
        <TmSubbarSpacer />
        {savedAt && serverLast4 && (
          <TmStatusPill tone="ok">
            {t(locale, "settings.byok.saved_as").replace("{last4}", serverLast4)}
          </TmStatusPill>
        )}
      </TmSubbar>

      {/* Intro pane */}
      <TmPane title="SETTINGS / BYOK" meta={preset.help}>
        <p className="px-3 py-2.5 font-tm-mono text-[11.5px] leading-relaxed text-tm-fg-2">
          {zh
            ? "你的 API key 经 AES-256-GCM 加密后保存在服务端。每次 LLM 请求时服务器解密并以 X-LLM-* header 形式传递给 LiteLLM，明文 key 不会被记录。"
            : "Your API key is encrypted with AES-256-GCM and stored server-side. On each LLM call the server decrypts it and passes it as X-LLM-* headers to LiteLLM. The plaintext key is never logged."}
        </p>
      </TmPane>

      {/* Credentials form pane — flat tm-form layout */}
      <TmPane
        title="CREDENTIALS"
        meta={
          <span className="tabular-nums">
            {provider} · {effectiveBase}
          </span>
        }
      >
        <div className="flex flex-col gap-3 px-3 py-3">
          {/* Provider — chip row instead of dropdown so all 4 options
              are visible at once and clicking any switches without
              opening a menu. */}
          <div className="flex flex-col gap-1">
            <label className={FORM_LABEL}>
              {zh ? "服务商 / PROVIDER" : "PROVIDER"}
            </label>
            <div className="flex flex-wrap gap-1">
              {PROVIDER_VALUES.map((p) => {
                const active = p === provider;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setProvider(p);
                      setTestState({ kind: "idle" });
                    }}
                    className={
                      active
                        ? "border border-tm-accent bg-tm-accent-soft px-2 py-0.5 font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-accent"
                        : "border border-tm-rule bg-tm-bg-2 px-2 py-0.5 font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-fg-2 hover:text-tm-fg"
                    }
                  >
                    {PROVIDER_PRESETS[p].label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* API Key with reveal toggle inline */}
          <div className="flex flex-col gap-1">
            <label className={FORM_LABEL}>API KEY</label>
            <div className="flex gap-1">
              <input
                type={revealKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  provider === "ollama"
                    ? zh ? "Ollama 不需要 key（任意填写）" : "not required for Ollama"
                    : "sk-..."
                }
                className={FORM_INPUT}
              />
              <button
                type="button"
                onClick={() => setRevealKey((r) => !r)}
                className="border border-tm-rule px-2 font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-fg"
              >
                {revealKey
                  ? zh ? "隐藏" : "HIDE"
                  : zh ? "显示" : "REVEAL"}
              </button>
            </div>
          </div>

          {/* Side-by-side base + model — `tm-form .row` pattern */}
          <div className="flex gap-2">
            <div className="flex flex-1 flex-col gap-1">
              <label className={FORM_LABEL}>
                {zh ? "BASE URL（可选）" : "BASE URL (optional)"}
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={preset.defaultBase}
                className={FORM_INPUT}
              />
            </div>
            <div className="flex flex-1 flex-col gap-1">
              <label className={FORM_LABEL}>
                {zh ? "模型 ID（可选）" : "MODEL ID (optional)"}
              </label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={preset.defaultModel}
                className={FORM_INPUT}
              />
            </div>
          </div>

          <p className="font-tm-mono text-[10.5px] text-tm-muted">
            {zh ? "实际请求：" : "request will use: "}
            <span className="text-tm-fg-2">
              {provider} · {effectiveBase} · {effectiveModel}
            </span>
          </p>

          {/* M4b D1: nudge that Rich brief is now consumable. The actual button */}
          {/* lives on /stock/[ticker], RichThesis component. */}
          <div className="text-xs text-tm-muted">
            {hasByok()
              ? t(locale, "settings.byok.rich_brief_unlocked")
              : t(locale, "settings.byok.rich_brief_locked")}
          </div>
        </div>

        {/* tm-form-foot — action bar separated by hairline */}
        <div className="flex flex-wrap items-center gap-2 border-t border-tm-rule px-3 py-2">
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

          {testState.kind === "ok" && (
            <TmStatusPill tone="ok">
              {zh
                ? `✓ 连通正常 ${testState.ms}ms · ${testState.tokens.prompt} / ${testState.tokens.completion} tokens`
                : `✓ CONNECTED · ${testState.ms}ms · ${testState.tokens.prompt} / ${testState.tokens.completion} tokens`}
            </TmStatusPill>
          )}
          {testState.kind === "fail" && (
            <TmStatusPill tone="err">
              {zh ? "✗ 失败：" : "✗ FAILED: "}
              {testState.status ? `HTTP ${testState.status} · ` : ""}
              {testState.message}
            </TmStatusPill>
          )}
        </div>
      </TmPane>

      {/* Notes pane — origin-scoping warnings */}
      <TmPane title="NOTES">
        <ul className="flex flex-col gap-1 px-3 py-2.5 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
          <li>
            {zh
              ? "localStorage 仅在本浏览器、本域名下可见。换浏览器或换设备需要重新填写。"
              : "localStorage is scoped to this browser and origin. Re-enter on a different browser or device."}
          </li>
          <li>
            {zh
              ? "preview 部署 URL 与 production 是不同 origin，凭证不会跨越。"
              : "Vercel preview URLs and production are separate origins; credentials do not carry across."}
          </li>
        </ul>
      </TmPane>

      {/* Signal weights override — JSON editor stored in localStorage */}
      <TmPane
        title="SIGNAL WEIGHTS OVERRIDE"
        meta={zh ? "M3: localStorage · M4+ 同步至服务端" : "M3: localStorage · M4+ syncs to server"}
      >
        <WeightsEditor />
      </TmPane>

      {/* Watchlist — localStorage ticker list used by alerts + cron priority */}
      <TmPane
        title="WATCHLIST"
        meta={zh ? "intraday cron 优先处理 + /alerts 显示" : "intraday cron prioritisation + /alerts display"}
      >
        <WatchlistEditor />
      </TmPane>

      {/* Danger zone */}
      <TmPane
        title={t(locale, "settings.danger.title").toUpperCase()}
        meta={zh ? "不可撤销操作" : "irreversible actions"}
      >
        <div className="flex flex-col gap-4 px-3 py-3">
          {/* Export */}
          <div className="flex items-center gap-3">
            <TmButton
              variant="secondary"
              onClick={() => { void handleExport(); }}
              disabled={exportInProgress}
            >
              {exportInProgress
                ? zh ? "导出中…" : "EXPORTING…"
                : t(locale, "settings.danger.export").toUpperCase()}
            </TmButton>
            <span className="font-tm-mono text-[10.5px] text-tm-muted">
              {zh ? "下载 JSON 数据包" : "downloads a JSON data bundle"}
            </span>
          </div>

          {/* Delete account */}
          <div className="flex flex-col gap-2 border border-red-800/40 bg-red-950/20 p-3">
            <p className="font-tm-mono text-[10.5px] font-semibold uppercase tracking-[0.06em] text-red-400">
              {t(locale, "settings.danger.delete")}
            </p>
            <p className="font-tm-mono text-[10.5px] text-tm-muted">
              {t(locale, "settings.danger.delete_confirm")}
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.value)}
                placeholder="DELETE"
                className="h-7 w-36 bg-tm-bg-2 border border-tm-rule px-2 font-tm-mono text-[11.5px] text-tm-fg outline-none placeholder:text-tm-muted focus:border-red-500"
              />
              <TmButton
                variant="ghost"
                onClick={() => { void handleDeleteAccount(); }}
                disabled={deleteConfirm !== "DELETE" || deleteInProgress}
              >
                {deleteInProgress
                  ? zh ? "删除中…" : "DELETING…"
                  : t(locale, "settings.danger.delete").toUpperCase()}
              </TmButton>
            </div>
          </div>
        </div>
      </TmPane>
    </TmScreen>
  );
}
