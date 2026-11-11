"use client";

/**
 * Settings page — BYOK credential management.
 *
 * Phase 2 (BYOK): the open-source deploy of alpha-agent doesn't supply
 * an LLM key on the public endpoint. Visitors paste their own provider
 * credentials here; the canonical copy is encrypted server-side. Legacy
 * localStorage credentials can be imported once and then removed.
 *
 * Stage 3 redesign — re-port to match the design's actual workstation
 * layout (full-width edge-to-edge `tm-screen` with stacked panes
 * separated by hairlines, NOT centred rounded cards). Form fields use
 * the `tm-form` flat label-stacked pattern; actions sit in a hairline
 * `tm-form-foot` bar at the bottom of the credentials pane. ALL
 * business logic preserved verbatim.
 */

import { useCallback, useEffect, useState } from "react";
import { signOut } from "next-auth/react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmStatusPill } from "@/components/tm/TmSubbar";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { TmToggleGroup } from "@/components/tm/TmToggleGroup";
import { TmFieldShell, TmInput } from "@/components/tm/TmField";
import {
  type LLMProvider,
  PROVIDER_PRESETS,
  clearByok,
  loadByok,
} from "@/lib/byok";
import {
  getByok,
  saveByok as saveByokServer,
  testByok,
  deleteByok as deleteByokServer,
  deleteAccount,
  exportAccount,
  type ByokGetResponse,
} from "@/lib/api/user";
import { savedConnectionMatches } from "@/components/settings/connection-state";
import { t } from "@/lib/i18n";
import WeightsEditor from "@/components/settings/WeightsEditor";
import WatchlistEditor from "@/components/settings/WatchlistEditor";
import ChangeLog from "@/components/settings/ChangeLog";
import { connectionTestStatus, providerDisplay, readLastConnectionTest, writeLastConnectionTest, type LastConnectionTest } from "@/components/settings/connection-state";
import { BrainCredentialsCard } from "@/components/settings/BrainCredentialsCard";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";

type TestState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; ms: number; tokens: { prompt: number; completion: number } }
  | { kind: "fail"; status: number | null; message: string };

const PROVIDER_VALUES: ReadonlyArray<LLMProvider> = ["openai", "kimi", "ollama", "anthropic"];
type SettingsSection = "llm" | "brain" | "preferences" | "history" | "account";

export default function SettingsPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [section, setSection] = useState<SettingsSection>("llm");
  const [savedConnection, setSavedConnection] = useState<ByokGetResponse | null>(null);
  const [connectionLoading, setConnectionLoading] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [accountError, setAccountError] = useState("");
  const [showDelete, setShowDelete] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [localCleanupWarning, setLocalCleanupWarning] = useState(false);

  const [provider, setProvider] = useState<LLMProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [revealKey, setRevealKey] = useState(false);
  const [testState, setTestState] = useState<TestState>({ kind: "idle" });
  const [lastTest, setLastTest] = useState<LastConnectionTest | null>(null);
  useEffect(() => { setLastTest(readLastConnectionTest()); }, []);
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

  const loadConnection = useCallback(async () => {
    setConnectionLoading(true);
    setConnectionError("");
    try {
      const resp = await getByok();
      setSavedConnection(resp);
      setServerLast4(resp?.last4 ?? null);
      setApiKey(""); setRevealKey(false);
      if (resp && PROVIDER_VALUES.includes(resp.provider as LLMProvider)) {
        setProvider(resp.provider as LLMProvider);
        setBaseUrl(resp.base_url ?? "");
        setModel(resp.model ?? "");
      }
      // Never load a legacy plaintext key into a visible editing field.
      setShowImportBanner(!resp && Boolean(loadByok()));
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    } finally { setConnectionLoading(false); }
  }, []);
  useEffect(() => { void loadConnection(); }, [loadConnection]);

  const preset = PROVIDER_PRESETS[provider];
  const effectiveBase = baseUrl.trim() || preset.defaultBase;
  const effectiveModel = model.trim() || preset.defaultModel;
  const canSave = !connectionLoading && !connectionError && (provider === "ollama" || apiKey.trim().length > 4);
  const sameSavedConnection = savedConnectionMatches(savedConnection, provider, effectiveBase, effectiveModel);
  const connectionBusy = saving || clearing || importBusy || historyBusy || testState.kind === "running";
  const dirtyConnection = Boolean(apiKey.trim()) || (savedConnection !== null ? !sameSavedConnection : provider !== "openai" || Boolean(baseUrl.trim()) || Boolean(model.trim()));
  const canTest = !connectionLoading && !connectionError && (canSave || (sameSavedConnection && !apiKey.trim()));
  function resetFeedback() { setTestState({kind:"idle"}); setSavedAt(null); }
  function clearLocalCredential() {
    try { clearByok(); setLocalCleanupWarning(false); }
    catch { setLocalCleanupWarning(true); }
  }
  function recordSaved(resp: {provider: string; last4: string; encrypted_at: string}) {
    setSavedConnection({...resp, model:model.trim() || null, base_url:baseUrl.trim() || null, last_used_at:savedConnection?.provider === resp.provider ? savedConnection.last_used_at : null});
    setServerLast4(resp.last4); setApiKey(""); setRevealKey(false);
    clearLocalCredential(); setShowImportBanner(false);
    setSavedAt(new Date().toLocaleTimeString());
  }

  async function handleSave() {
    if (!canSave || connectionBusy) return;
    setSaving(true);
    // Store server-side; clear the editing field after a successful save.
    try {
      const resp = await saveByokServer({
        provider,
        api_key: apiKey.trim() || "ollama",
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      recordSaved(resp);
    } catch (err) {
      setSavedAt(null);
      setTestState({
        kind: "fail",
        status: null,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally { setSaving(false); }
  }

  async function handleImport() {
    if (connectionBusy || connectionLoading) return;
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
      clearLocalCredential();
      setShowImportBanner(false);
      await loadConnection();
    } catch (err) {
      setTestState({
        kind: "fail",
        status: null,
        message: err instanceof Error ? err.message : zh ? "导入失败" : "Import failed",
      });
    } finally {
      setImportBusy(false);
    }
  }

  function handleDiscardImport() {
    clearLocalCredential();
    setShowImportBanner(false);
  }

  async function handleExport() {
    setExportInProgress(true);
    setAccountError("");
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
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : zh ? "导出失败" : "Export failed");
    } finally {
      setExportInProgress(false);
    }
  }

  async function handleDeleteAccount() {
    if (deleteConfirm !== "DELETE") return;
    setDeleteInProgress(true);
    setAccountError("");
    try {
      await deleteAccount();
      await signOut({ callbackUrl: "/signin" });
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : zh ? "账号删除失败" : "Account deletion failed");
      setDeleteInProgress(false);
    }
  }

  async function handleClear() {
    if (connectionBusy) return;
    setClearing(true);
    try {
      await deleteByokServer();
      clearLocalCredential();
      setProvider("openai");
      setApiKey("");
      setBaseUrl("");
      setModel("");
      setServerLast4(null);
      setSavedConnection(null);
      setSavedAt(null);
      setTestState({ kind: "idle" });
    } catch (exc) {
      setTestState({
        kind: "fail",
        status: null,
        message: exc instanceof Error ? exc.message : String(exc),
      });
    } finally { setClearing(false); setConfirmClear(false); }
  }

  // Live test: save first, then exercise a dedicated minimal chat probe.
  // Connectivity is intentionally decoupled from factor JSON generation so
  // schema/prompt failures are not misreported as credential failures.
  async function handleTest() {
    if (!canTest || connectionBusy) return;
    setTestState({ kind: "running" });
    const started = performance.now();
    try {
      if (!sameSavedConnection || apiKey.trim()) {
      const resp = await saveByokServer({
        provider,
        api_key: apiKey.trim() || "ollama",
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      recordSaved(resp);
      }
      const data = await testByok();
      const elapsed = Math.max(data.latency_ms, Math.round(performance.now() - started));
      setLastTest(writeLastConnectionTest(true));
      setTestState({
        kind: "ok",
        ms: elapsed,
        tokens: {
          prompt: data.prompt_tokens,
          completion: data.completion_tokens,
        },
      });
      // Read back usage metadata without replacing the user's editable draft.
      try { setSavedConnection(await getByok()); } catch { /* Test succeeded; metadata refresh is non-critical. */ }
    } catch (exc) {
      setLastTest(writeLastConnectionTest(false));
      setTestState({
        kind: "fail",
        status: null,
        message: exc instanceof Error ? exc.message : String(exc),
      });
    }
  }

  const sectionItems = [
    {key:"llm" as const,label:zh ? "模型连接" : "Model connection"},
    {key:"brain" as const,label:"WorldQuant BRAIN"},
    {key:"preferences" as const,label:zh ? "研究偏好" : "Research preferences"},
    {key:"history" as const,label:zh ? "变更记录" : "Change history"},
    {key:"account" as const,label:zh ? "账户与数据" : "Account & data"},
  ];
  return <TmScreen className="[&>*]:shrink-0">
    <WorkbenchHeader eyebrow={zh ? "参考 · 运行配置" : "Reference · Runtime configuration"}
      title={zh ? "设置" : "Settings"}
      subtitle={zh ? "连接你的研究工具，管理自己的偏好与数据。" : "Connect your research tools. Manage your preferences and data."}
      statuses={[
        {label:zh ? "已保存服务商" : "Saved provider",value:savedConnection?.provider.toUpperCase() ?? "—"},
        {label:zh ? "服务端凭据" : "Server credential",value:connectionLoading ? (zh ? "读取中" : "Loading") : connectionError ? (zh ? "待确认" : "Unknown") : serverLast4 ? (zh ? "已加密保存" : "Encrypted") : (zh ? "未配置" : "None"),tone:!connectionError && serverLast4 ? "positive" : "warning"},
        {label:zh ? "连接测试" : "Connection test",...connectionTestStatus(testState, lastTest, zh)},
      ]}/>
    <SegmentedTabs items={sectionItems} active={section} onChange={next=>{if(!connectionBusy)setSection(next);}} idBase="settings-section" ariaLabel={zh ? "设置分类" : "Settings sections"}/>
    <section id="settings-section-panel-llm" role="tabpanel" aria-labelledby="settings-section-tab-llm" hidden={section !== "llm"}>
      {showImportBanner && <div className="flex flex-wrap items-center gap-3 border-b border-tm-rule bg-tm-accent-soft p-4 text-sm">
        <p className="flex-1">{t(locale,"settings.byok.import_banner")}</p>
        <TmButton variant="secondary" disabled={importBusy || connectionBusy} loading={importBusy} onClick={()=>void handleImport()}>{t(locale,"settings.byok.import_button")}</TmButton>
        <TmButton variant="ghost" disabled={importBusy || connectionBusy} onClick={handleDiscardImport}>{t(locale,"settings.byok.discard_button")}</TmButton>
      </div>}
      <div className="grid min-w-0 items-start xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <TmPane title={zh ? "LLM 连接" : "LLM connection"} meta={dirtyConnection ? (zh ? "有未保存修改" : "Unsaved changes") : "BYOK"} className="xl:border-r xl:border-tm-rule">
          <div className="space-y-5 p-5 md:p-6">
            <p className="max-w-[70ch] text-sm leading-6 text-tm-fg-2">{zh ? "使用你自己的模型账号。密钥加密保存在服务端，已保存密钥不会回传到页面。" : "Use your own model account. Keys are encrypted on the server and saved keys are never returned to this page."}</p>
            {connectionError && <div role="alert" className="border-l-2 border-tm-warn bg-tm-warn-soft p-3 text-sm"><p>{zh ? "暂时无法读取连接，请重试后再编辑。" : "Could not load the saved connection. Retry before editing."}</p><p className="mt-1 break-words text-xs text-tm-muted">{connectionError}</p><TmButton variant="secondary" className="mt-2" onClick={()=>void loadConnection()}>{zh ? "重新读取" : "Retry"}</TmButton></div>}
            <fieldset disabled={connectionLoading || Boolean(connectionError) || connectionBusy || importBusy} className="min-w-0 space-y-4 disabled:opacity-60">
              <TmFieldShell label={zh ? "服务商" : "Provider"}>
                <TmToggleGroup value={provider} options={PROVIDER_VALUES.map(value=>({value,label:PROVIDER_PRESETS[value].label}))}
                  onChange={value=>{setProvider(value);setBaseUrl("");setModel("");setApiKey("");setRevealKey(false);resetFeedback();}}
                  ariaLabel={zh ? "服务商" : "Provider"} className="flex-wrap"/>
              </TmFieldShell>
              <TmFieldShell label={zh ? "API 密钥" : "API key"} htmlFor="settings-api-key">
                <div className="flex gap-2">
                  <TmInput id="settings-api-key" type={revealKey ? "text" : "password"} value={apiKey} onChange={value=>{setApiKey(value);resetFeedback();}} autoComplete="off"
                    placeholder={provider === "ollama" ? (zh ? "无需密钥" : "No key required") : serverLast4 ? (zh ? "留空保留已保存密钥；替换时填入新密钥" : "Leave blank to retain; enter a new key to replace") : "sk-…"} className="min-w-0 flex-1"/>
                  <TmButton variant="secondary" onClick={()=>setRevealKey(value=>!value)} disabled={!apiKey} aria-pressed={revealKey}>{revealKey ? (zh ? "隐藏" : "Hide") : (zh ? "显示" : "Show")}</TmButton>
                </div>
              </TmFieldShell>
              <div className="grid min-w-0 gap-4 md:grid-cols-2">
                <TmInput label={zh ? "API 地址（可选）" : "API base URL (optional)"} value={baseUrl} onChange={value=>{setBaseUrl(value);resetFeedback();}} placeholder={preset.defaultBase}/>
                <TmInput label={zh ? "模型 ID（可选）" : "Model ID (optional)"} value={model} onChange={value=>{setModel(value);resetFeedback();}} placeholder={preset.defaultModel}/>
              </div>
            </fieldset>
            <div className="border-l-2 border-tm-rule-2 pl-3 text-xs leading-6 text-tm-muted">
              <p>{zh ? "当前表单地址" : "Draft endpoint"} <span className="break-all font-tm-mono text-tm-fg-2">{effectiveBase}</span></p>
              <p>{zh ? "当前表单模型" : "Draft model"} <span className="break-all font-tm-mono text-tm-fg-2">{effectiveModel}</span></p>
              {dirtyConnection && !canSave && <p className="text-tm-warn">{zh ? "更改服务商、地址或模型时，请重新输入密钥后保存。" : "Re-enter the key to save a changed provider, endpoint or model."}</p>}
              {provider === "ollama" && <p>{zh ? "地址须能被平台服务器访问；localhost 指平台服务器，不是你的电脑。" : "The endpoint must be reachable from the platform server. localhost refers to that server, not your computer."}</p>}
            </div>
          </div>
          {localCleanupWarning && <p role="alert" className="px-5 pb-3 text-sm text-tm-warn">{zh ? "服务端操作已完成，但浏览器禁止清除本机旧凭据。请允许本地存储后重试清理。" : "The server operation completed, but this browser blocked legacy-key cleanup. Allow local storage, then retry cleanup."}<TmButton variant="ghost" onClick={clearLocalCredential}>{zh ? "重试本机清理" : "Retry local cleanup"}</TmButton></p>}
          <div className="flex flex-wrap items-center gap-2 border-t border-tm-rule bg-tm-bg-2/40 px-5 py-3">
            <TmButton variant="primary" onClick={()=>void handleSave()} disabled={!canSave || connectionBusy || importBusy} loading={saving} loadingLabel={zh ? "保存中…" : "Saving…"}>{zh ? "保存连接" : "Save connection"}</TmButton>
            <TmButton variant="secondary" onClick={()=>void handleTest()} disabled={!canTest || connectionBusy || importBusy} loading={testState.kind === "running"} loadingLabel={zh ? "测试中…" : "Testing…"}>{canSave && (dirtyConnection || !savedConnection) ? (zh ? "保存并测试" : "Save & test") : (zh ? "测试已保存连接" : "Test saved connection")}</TmButton>
            {dirtyConnection && savedConnection && <TmButton variant="ghost" disabled={connectionBusy} onClick={()=>{setApiKey("");setRevealKey(false);resetFeedback();void loadConnection();}}>{zh ? "撤销修改" : "Discard edits"}</TmButton>}
            {serverLast4 && <TmButton variant="ghost" className="ml-auto" disabled={connectionBusy} onClick={()=>setConfirmClear(true)}>{zh ? "移除凭据" : "Remove credential"}</TmButton>}
            {savedAt && <span role="status" className="text-xs text-tm-pos">{zh ? "已保存" : "Saved"} {savedAt}</span>}
          </div>
          {testState.kind === "running" && <p role="status" className="border-t border-tm-rule px-5 py-3 text-sm text-tm-muted">{zh ? "正在向模型发送最小请求；服务商可能需要一些响应时间。" : "Sending a minimal request; your provider may need some response time."}</p>}
          {testState.kind === "ok" && <p role="status" className="border-t border-tm-rule px-5 py-3 font-tm-mono text-xs text-tm-pos">{zh ? "连接测试通过" : "Connection test passed"} · {testState.ms.toLocaleString()} ms · {(testState.tokens.prompt+testState.tokens.completion).toLocaleString()} tokens</p>}
          {testState.kind === "fail" && <p role="alert" className="break-words border-t border-tm-rule px-5 py-3 text-sm leading-6 text-tm-neg">{testState.message}</p>}
        </TmPane>
        <aside className="min-w-0">
          <TmPane title={zh ? "已保存连接" : "Saved connection"} bodyClassName="p-5 space-y-4">
            <TmStatusPill tone={serverLast4 && !connectionError ? "ok" : "warn"}>{connectionLoading ? (zh ? "读取中" : "Loading") : connectionError ? (zh ? "状态待确认" : "Status unknown") : serverLast4 ? (zh ? "凭据已保存，连接另行测试" : "Stored; test connectivity separately") : (zh ? "尚未配置" : "Not configured")}</TmStatusPill>
            <dl className="space-y-3 font-tm-mono text-xs">{[
              [zh ? "服务商" : "Provider",savedConnection ? providerDisplay(savedConnection.provider, savedConnection.base_url, zh) : "—"],
              [zh ? "模型" : "Model",savedConnection ? savedConnection.model || PROVIDER_PRESETS[savedConnection.provider as LLMProvider]?.defaultModel || "—" : "—"],
              [zh ? "API 地址" : "Endpoint",savedConnection ? savedConnection.base_url || PROVIDER_PRESETS[savedConnection.provider as LLMProvider]?.defaultBase || "—" : "—"],
              [zh ? "密钥尾号" : "Key suffix",serverLast4 ? "•••• "+serverLast4 : "—"],
              [zh ? "最近使用" : "Last used",savedConnection?.last_used_at ? new Date(savedConnection.last_used_at).toLocaleString(zh ? "zh-CN" : "en-US") : (zh ? "暂无记录" : "No record")],
            ].map(([label,value])=><div key={label} className="grid grid-cols-[92px_minmax(0,1fr)] gap-3"><dt className="text-tm-muted">{label}</dt><dd className="break-words text-tm-fg">{value}</dd></div>)}</dl>
          </TmPane>
          <TmPane title={zh ? "此连接用于" : "Used by"} bodyClassName="divide-y divide-tm-rule px-5">{[
            ["/alpha",zh ? "因子表达式翻译" : "Factor translation",zh ? "把研究假设转为可检验的表达式。" : "Translate a hypothesis into a testable expression."],
            ["/picks",zh ? "个股 Rich Brief" : "Stock Rich Brief",zh ? "打开股票详情，按需生成研究说明。" : "Open stock details for an on-demand research brief."],
            ["/paper",zh ? "机器人模拟投资" : "Paper investing bot",zh ? "使用保存的模型管理独立模拟账户。" : "Use the saved model in a separate paper account."],
          ].map(([href,title,body])=><div key={href} className="py-4"><TmLinkButton href={href} prefetch={false} variant="ghost" className="px-0">{title} →</TmLinkButton><p className="mt-1 text-xs leading-6 text-tm-muted">{body}</p></div>)}</TmPane>
          <p className="px-5 py-4 text-xs leading-6 text-tm-muted">{zh ? "模型费用由服务商收取。BRAIN 登录信息独立保存，移除 LLM 凭据不会影响 BRAIN。" : "Model usage is billed by your provider. BRAIN credentials are stored separately and unaffected by LLM credential removal."}</p>
        </aside>
      </div>
    </section>
    <section id="settings-section-panel-brain" role="tabpanel" aria-labelledby="settings-section-tab-brain" hidden={section !== "brain"}>
      <div className="max-w-[980px]"><BrainCredentialsCard/></div>
    </section>
    <section id="settings-section-panel-preferences" role="tabpanel" aria-labelledby="settings-section-tab-preferences" hidden={section !== "preferences"}>
      <div className="grid items-start xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,1fr)]">
        <TmPane title={zh ? "信号权重" : "Signal weights"} meta={zh ? "仅本浏览器" : "This browser only"} className="xl:border-r xl:border-tm-rule">
          <p className="px-5 pt-4 text-sm leading-6 text-tm-muted">{zh ? "调整本机展示的相对权重，不改写全平台策略或历史推荐。" : "Adjust local display weights without changing global policies or historical recommendations."}</p><WeightsEditor/>
        </TmPane>
        <TmPane title={zh ? "关注列表" : "Watchlist"} meta={zh ? "警报与研究" : "Alerts & research"}><WatchlistEditor/></TmPane>
      </div>
    </section>
    <section id="settings-section-panel-history" role="tabpanel" aria-labelledby="settings-section-tab-history" hidden={section !== "history"}>
      <TmPane title={zh ? "系统配置变更" : "Configuration changes"} meta={zh ? "最近 50 条" : "Latest 50 records"}>
        <p className="px-5 py-3 text-xs leading-6 text-tm-muted">{zh ? "包括模型连接与线上因子表达式等系统配置。只有模型名称和 API 地址可在此回滚；回滚会产生一条新记录，不恢复或展示旧密钥。" : "Includes model connection and system settings such as the live factor expression. Only model and endpoint can be rolled back here; a rollback adds a record and never restores or reveals an old key."}</p>
        {dirtyConnection && <p className="px-5 pb-3 text-sm text-tm-warn">{zh ? "模型连接有未保存修改，请先保存或撤销，再执行回滚。" : "Save or discard connection edits before applying a rollback."}</p>}
        <ChangeLog disabled={connectionBusy || dirtyConnection} onBusyChange={setHistoryBusy} onApplied={()=>{resetFeedback();void loadConnection();}}/>
      </TmPane>
    </section>
    <section id="settings-section-panel-account" role="tabpanel" aria-labelledby="settings-section-tab-account" hidden={section !== "account"}>
      <TmPane title={zh ? "账户数据" : "Account data"} className="max-w-[980px]" bodyClassName="space-y-6 p-5">
        <div className="flex flex-wrap items-center gap-4"><TmButton variant="secondary" onClick={()=>void handleExport()} disabled={exportInProgress || deleteInProgress} loading={exportInProgress} loadingLabel={zh ? "导出中…" : "Exporting…"}>{t(locale,"settings.danger.export")}</TmButton><p className="text-sm text-tm-muted">{zh ? "下载账户 JSON 数据包，不删除或重置账户。不含因子库（只存在本浏览器，请在因子库页单独导出）。" : "Download your account JSON bundle without deleting or resetting it. The factor library lives only in this browser; export it from the Zoo page."}</p></div>
        <div className="space-y-3 border-t border-tm-rule pt-5">
          <h2 className="font-tm-mono text-sm font-semibold text-tm-neg">{t(locale,"settings.danger.delete")}</h2>
          <p className="max-w-[65ch] text-sm leading-6 text-tm-muted">{zh ? "永久删除当前账户及其服务端个人数据。这不是清除凭据，也不是重置模拟仓，执行后无法撤销。" : "Permanently remove your account and its server-side personal data. This is not a credential removal or a paper-account reset, and cannot be undone."}</p>
          <TmButton variant="secondary" className="text-tm-neg" aria-expanded={showDelete} onClick={()=>{setShowDelete(value=>!value);setDeleteConfirm("");}}>{showDelete ? (zh ? "收起删除确认" : "Hide deletion confirmation") : (zh ? "查看删除确认" : "Review account deletion")}</TmButton>
          {showDelete && <div className="space-y-3 border-l-2 border-tm-neg pl-4">
            <div className="flex flex-wrap items-end gap-3"><TmInput label={zh ? "输入 DELETE 确认" : "Type DELETE to confirm"} value={deleteConfirm} onChange={setDeleteConfirm} autoComplete="off" className="w-52"/>
              <TmButton variant="danger" onClick={()=>void handleDeleteAccount()} disabled={deleteConfirm !== "DELETE" || deleteInProgress || exportInProgress} loading={deleteInProgress}>{t(locale,"settings.danger.delete")}</TmButton></div>
          </div>}
        </div>
        {accountError && <p role="alert" className="break-words text-sm text-tm-neg">{accountError}</p>}
      </TmPane>
    </section>
    <TmDialog open={confirmClear} onClose={()=>{if(!clearing)setConfirmClear(false);}} title={zh ? "移除 LLM 凭据？" : "Remove the LLM credential?"} closeLabel={zh ? "取消" : "Cancel"} className="max-w-[640px]">
      <p className="text-sm leading-7">{zh ? "模型相关功能将无法使用该连接，直到重新配置。研究记录、模拟仓和独立保存的 BRAIN 登录信息不会删除。" : "Model-backed features will lose this connection until it is configured again. Research records, paper accounts and the separately saved BRAIN login remain unchanged."}</p>
      <div className="mt-5 flex justify-end gap-2"><TmButton variant="secondary" disabled={clearing} onClick={()=>setConfirmClear(false)}>{zh ? "保留" : "Keep"}</TmButton><TmButton variant="danger" disabled={clearing} loading={clearing} onClick={()=>void handleClear()}>{zh ? "确认移除" : "Remove credential"}</TmButton></div>
    </TmDialog>
  </TmScreen>;
}
