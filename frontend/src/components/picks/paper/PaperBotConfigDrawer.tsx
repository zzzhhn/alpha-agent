"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmDrawer } from "@/components/tm/TmDrawer";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmInput, TmTextarea, TmCheckbox, TmSelect } from "@/components/tm/TmField";
import { createPaperBotAccount, patchPaperBotConfig, type PaperAccountSummary, type PaperBotConfig } from "@/lib/api/paper-bot";
import { t } from "@/lib/i18n";
import { getByok } from "@/lib/api/user";

export default function PaperBotConfigDrawer({ open, onClose, account, config, onSaved }: {
  readonly open: boolean; readonly onClose: () => void;
  readonly account: PaperAccountSummary | null; readonly config: PaperBotConfig | null;
  readonly onSaved: (account: PaperAccountSummary) => void;
}) {
  const { locale } = useLocale();
  const [name,setName] = useState("");
  const [cash,setCash] = useState("100000");
  const [provider,setProvider] = useState("");
  const [model,setModel] = useState("");
  const [instructions,setInstructions] = useState("");
  const [schedule,setSchedule] = useState(false);
  const [atOpen,setAtOpen] = useState(true);
  const [atClose,setAtClose] = useState(true);
  const [openMinutes,setOpenMinutes] = useState("30");
  const [closeMinutes,setCloseMinutes] = useState("30");
  const [daily,setDaily] = useState("6");
  const [positions,setPositions] = useState("8");
  const [weight,setWeight] = useState("25");
  const [fees,setFees] = useState("10");
  const [slippage,setSlippage] = useState("5");
  const [horizon,setHorizon] = useState("20");
  const [researchAge,setResearchAge] = useState("3");
  const [tradeDelta,setTradeDelta] = useState("0");
  const [turnover,setTurnover] = useState("200");
  const [busy,setBusy] = useState(false);
  const [byokLoading,setByokLoading] = useState(false);
  const [error,setError] = useState<string | null>(null);
  // Retain a successful creation if the following PATCH fails. Retrying never creates another account.
  const [created,setCreated] = useState<PaperAccountSummary | null>(null);
  const initialized=useRef(false);
  useEffect(() => {
    if (!open || initialized.current) return;
    initialized.current=true;
    setError(null); setCreated(null);
    setName(account?.name ?? t(locale,"sim.bot.account_default"));
    setCash(String(account?.initial_cash ?? 100000));
    setProvider(config?.provider ?? ""); setModel(config?.model ?? "");
    setInstructions(config?.instructions ?? ""); setSchedule(config?.schedule_enabled ?? false);
    setAtOpen(config?.open_enabled ?? true); setAtClose(config?.close_enabled ?? true);
    setOpenMinutes(String(config?.open_offset_minutes ?? 30)); setCloseMinutes(String(config?.close_offset_minutes ?? 30));
    setDaily(String(config?.max_daily_runs ?? 6)); setPositions(String(config?.max_positions ?? 8));
    setWeight(String((config?.max_position_weight ?? 0.25)*100));
    setFees(String(config?.fee_bps ?? 10)); setSlippage(String(config?.slippage_bps ?? 5));
    setHorizon(String(config?.horizon_sessions ?? 20)); setResearchAge(String(config?.max_research_age_sessions ?? 3));
    setTradeDelta(String((config?.min_trade_weight_delta ?? 0)*100)); setTurnover(String((config?.max_turnover_weight ?? 2)*100));
  }, [open, account, config, locale]);
  useEffect(() => {
    if (!open || account) return;
    let cancelled=false;
    setByokLoading(true);
    void getByok().then(saved=>{
      if (!cancelled && saved) {setProvider(previous=>previous || saved.provider);setModel(previous=>previous || saved.model || "");}
    }).catch(()=>{
      // The account/config endpoints remain authoritative if metadata cannot be read.
    }).finally(()=>{if(!cancelled)setByokLoading(false);});
    return ()=>{cancelled=true;};
  },[open,account]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || byokLoading) return;
    if (schedule && !atOpen && !atClose) {setError(t(locale,"sim.bot.schedule_select"));return;}
    setBusy(true); setError(null);
    let target = account ?? created;
    try {
      if (!target) { target = await createPaperBotAccount({name:name.trim(),initial_cash:Number(cash)}); setCreated(target); }
      await patchPaperBotConfig(target.account_id, {
        ...(provider.trim() ? {provider:provider.trim()} : {}), model:model.trim(),
        instructions, schedule_enabled:schedule, open_enabled:atOpen, close_enabled:atClose,
        open_offset_minutes:Number(openMinutes), close_offset_minutes:Number(closeMinutes), max_daily_runs:Number(daily),
        max_positions:Number(positions), max_position_weight:Number(weight)/100, fee_bps:Number(fees), slippage_bps:Number(slippage),
        horizon_sessions:Number(horizon), max_research_age_sessions:Number(researchAge),
        min_trade_weight_delta:Number(tradeDelta)/100, max_turnover_weight:Number(turnover)/100, cash_policy:"discretionary",
      });
      onSaved(target); onClose();
    } catch (reason) {
      setError(!account && target ? t(locale,"sim.bot.create_partial") : reason instanceof Error ? reason.message : t(locale,"sim.bot.unavailable"));
    } finally { setBusy(false); }
  }

  return <TmDrawer open={open} onClose={() => {if (!busy) onClose();}} title={t(locale,account || created ? "sim.bot.configure" : "sim.bot.create")} closeLabel={t(locale,"sim.bot.close")} width="lg" description={t(locale,"sim.bot.config_next")} footer={<div className="space-y-3">{error ? <p role="alert" className="break-words text-xs leading-5 text-tm-neg">{error}</p> : null}<div className="flex justify-end gap-2"><TmButton variant="secondary" disabled={busy} onClick={onClose}>{t(locale,"sim.bot.close")}</TmButton><TmButton type="submit" form="paper-bot-config" loading={busy || byokLoading} loadingLabel={t(locale,byokLoading ? "common.loading" : "sim.bot.saving")}>{t(locale,"sim.bot.save")}</TmButton></div></div>}>
    <form id="paper-bot-config" onSubmit={event => void save(event)} className="space-y-6">
      {!account ? <fieldset disabled={busy || !!created} className="grid grid-cols-1 gap-3 sm:grid-cols-2"><TmInput label={t(locale,"sim.bot.name")} value={name} onChange={setName} required maxLength={80} /><TmInput label={t(locale,"sim.bot.initial_cash")} value={cash} onChange={setCash} type="number" min={0.01} step={0.01} required /></fieldset> : null}
      <fieldset disabled={busy} className="space-y-3"><legend className="mb-3 text-sm font-semibold text-tm-fg">{t(locale,"sim.bot.model_strategy")}</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><TmSelect label={t(locale,"sim.bot.provider")} value={provider} onChange={setProvider} options={[{value:"",label:t(locale,"sim.bot.saved_model")},{value:"kimi",label:"Kimi"},{value:"openai",label:t(locale,"sim.bot.openai_compatible")},{value:"anthropic",label:"Anthropic"},{value:"ollama",label:"Ollama"}]} /><TmInput label={t(locale,"sim.bot.model")} value={model} onChange={setModel} placeholder={t(locale,"sim.bot.saved_model")} maxLength={120} /></div>
        <p className="text-xs leading-5 text-tm-muted">{config && provider && provider !== config.provider ? t(locale,"sim.bot.byok_provider_changed") : config?.credential_configured ? t(locale,"sim.bot.byok_ready") : !config ? t(locale,"sim.bot.saved_model") : t(locale,"sim.bot.byok_missing")} <TmLinkButton href="/settings">{t(locale,"sim.bot.settings")}</TmLinkButton></p>
        <TmTextarea label={t(locale,"sim.bot.instructions")} hint={t(locale,"sim.bot.instructions_hint")} value={instructions} onChange={setInstructions} rows={5} maxLength={2000} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><TmInput label={t(locale,"sim.bot.horizon_sessions")} value={horizon} onChange={setHorizon} type="number" min={1} max={252} step={1} required /><TmInput label={t(locale,"sim.bot.research_age_limit")} value={researchAge} onChange={setResearchAge} type="number" min={0} max={20} step={1} required /></div>
        <p className="text-xs leading-5 text-tm-muted">{t(locale,"sim.bot.cash_discretionary")}</p>
      </fieldset>
      <fieldset disabled={busy} className="space-y-3"><legend className="mb-3 text-sm font-semibold text-tm-fg">{t(locale,"sim.bot.wake_times")}</legend>
        <TmCheckbox label={t(locale,"sim.bot.schedule")} checked={schedule} onChange={setSchedule} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><TmCheckbox label={`${t(locale,"sim.bot.open_slot")} ${openMinutes} ${t(locale,"sim.bot.minutes")}`} checked={atOpen} onChange={setAtOpen} /><TmCheckbox label={`${t(locale,"sim.bot.close_slot")} ${closeMinutes} ${t(locale,"sim.bot.minutes")}`} checked={atClose} onChange={setAtClose} /></div>
        <p className="text-xs leading-5 text-tm-muted">{t(locale,"sim.bot.schedule_hint")}</p>
      </fieldset>
      <fieldset disabled={busy} className="space-y-3"><legend className="mb-3 text-sm font-semibold text-tm-fg">{t(locale,"sim.bot.budget")}</legend><TmInput label={t(locale,"sim.bot.daily_runs")} value={daily} onChange={setDaily} type="number" min={1} max={12} step={1} required /></fieldset>
      <details className="border-t border-tm-rule pt-4">
        <summary className="cursor-pointer text-sm text-tm-fg">{t(locale,"sim.bot.advanced")}</summary>
        <fieldset disabled={busy} className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TmInput label={t(locale,"sim.bot.max_positions")} value={positions} onChange={setPositions} type="number" min={1} max={20} step={1} required />
          <TmInput label={t(locale,"sim.bot.max_weight")} value={weight} onChange={setWeight} type="number" min={1} max={100} step={1} required />
          <TmInput label={t(locale,"sim.bot.min_trade_delta")} value={tradeDelta} onChange={setTradeDelta} type="number" min={0} max={25} step="any" required />
          <TmInput label={t(locale,"sim.bot.max_turnover")} value={turnover} onChange={setTurnover} type="number" min={0} max={200} step="any" required />
          <TmInput label={`${t(locale,"sim.bot.fee")} (bps)`} value={fees} onChange={setFees} type="number" min={0} max={100} step={1} required />
          <TmInput label={`${t(locale,"sim.bot.slippage")} (bps)`} value={slippage} onChange={setSlippage} type="number" min={0} max={100} step={1} required />
        </fieldset>
      </details>
    </form>
  </TmDrawer>;
}
