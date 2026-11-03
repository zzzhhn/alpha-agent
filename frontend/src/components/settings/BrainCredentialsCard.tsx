"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton } from "@/components/tm/TmButton";
import { TmFieldShell, TmInput } from "@/components/tm/TmField";
import {
  fetchBrainStatus,
  saveBrainCredentials,
  testBrainConnection,
  type BrainStatus,
} from "@/lib/api/brain";

type Busy = "idle" | "saving" | "testing";

/**
 * Phase E2 settings card: connect the user's WorldQuant BRAIN account. The
 * login is POSTed once to the encrypted vault (never returned); a Test button
 * authenticates to BRAIN to confirm it works. This is the gate that lets the
 * BRAIN mining loop (Phase E4) run under the user's account.
 */
export function BrainCredentialsCard() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [statusState, setStatusState] = useState<"loading" | "ready" | "failed">("loading");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState<Busy>("idle");
  const actionLock = useRef(false);
  const statusRequest = useRef(0);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  const loadStatus = useCallback(async () => {
    const request = ++statusRequest.current;
    setStatusState("loading");
    try {
      const next = await fetchBrainStatus();
      if (statusRequest.current !== request) return;
      setStatus(next);
      setStatusState("ready");
    } catch {
      if (statusRequest.current === request) setStatusState("failed");
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    return () => { statusRequest.current += 1; };
  }, [loadStatus]);

  async function onSave() {
    if (actionLock.current || !username.trim() || !password) return;
    actionLock.current = true;
    setBusy("saving");
    setMsg(null);
    try {
      const r = await saveBrainCredentials(username.trim(), password);
      statusRequest.current += 1;
      setStatus(r);
      setStatusState("ready");
      setPassword("");
      setReveal(false);
      setMsg({ kind: "ok", text: zh ? "已加密保存，尚未测试连接。" : "Stored encrypted. Connection not yet tested." });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      actionLock.current = false;
      setBusy("idle");
    }
  }

  async function onTest() {
    if (actionLock.current || statusState !== "ready" || !status?.connected) return;
    actionLock.current = true;
    setBusy("testing");
    setMsg(null);
    try {
      const r = await testBrainConnection();
      setMsg(
        r.ok
          ? { kind: "ok", text: zh ? "已验证：已保存的凭据可连接 BRAIN。" : "Verified: stored credentials connected to BRAIN." }
          : { kind: "err", text: r.error
            ? `${zh ? "连接测试失败：" : "Connection test failed: "}${r.error}`
            : (zh ? "连接测试失败。" : "Connection test failed.") },
      );
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      actionLock.current = false;
      setBusy("idle");
    }
  }

  const meta = statusState === "loading" ? (zh ? "正在读取凭据状态…" : "Loading credential status…")
    : statusState === "failed" ? (zh ? "凭据状态未知" : "Credential status unknown")
      : status?.connected ? `${zh ? "已保存凭据" : "Credentials stored"}${status.username_last4 ? ` · …${status.username_last4}` : ""}`
        : (zh ? "未保存凭据" : "No credentials stored");

  return (
    <TmPane title="WORLDQUANT.BRAIN" meta={<span role="status">{meta}</span>}>
      <div className="flex flex-col gap-3 px-3 py-3">
        <p className="font-tm-mono text-xs leading-relaxed text-tm-muted">
          {zh
            ? "登录凭据加密保存，仅在服务端使用。测试连接会使用已保存的凭据。"
            : "Login credentials are stored encrypted and used server-side. Testing uses the stored credentials."}
        </p>

        <TmInput
          label={zh ? "BRAIN 用户名 / 邮箱" : "BRAIN USERNAME / EMAIL"}
          fieldSize="sm"
          value={username}
          onChange={setUsername}
          placeholder={zh ? "你的 BRAIN 登录邮箱" : "your BRAIN login email"}
          autoComplete="off"
          disabled={busy !== "idle"}
        />

        <TmFieldShell label={zh ? "BRAIN 密码" : "BRAIN PASSWORD"} htmlFor="brain-password">
          <div className="flex gap-1">
            <TmInput
              id="brain-password"
              fieldSize="sm"
              type={reveal ? "text" : "password"}
              value={password}
              onChange={setPassword}
              placeholder="••••••••"
              className="min-w-0 flex-1"
              autoComplete="off"
              disabled={busy !== "idle"}
            />
            <TmButton
              type="button"
              variant="secondary"
              size="sm"
              disabled={busy !== "idle"}
              onClick={() => setReveal((r) => !r)}
            >
              {reveal ? (zh ? "隐藏" : "HIDE") : zh ? "显示" : "REVEAL"}
            </TmButton>
          </div>
        </TmFieldShell>

        <div className="flex flex-wrap gap-2">
          <TmButton
            onClick={onSave}
            disabled={busy !== "idle" || !username.trim() || !password}
            loading={busy === "saving"}
            loadingLabel={zh ? "保存中…" : "Saving…"}
          >
            {zh ? "保存" : "Save"}
          </TmButton>
          {statusState === "ready" && status?.connected ? (
            <TmButton
              variant="secondary"
              onClick={onTest}
              disabled={busy !== "idle"}
              loading={busy === "testing"}
              loadingLabel={zh ? "测试中…" : "Testing…"}
            >
              {zh ? "测试连接" : "Test connection"}
            </TmButton>
          ) : null}
          {statusState === "failed" ? (
            <TmButton variant="secondary" disabled={busy !== "idle"} onClick={() => void loadStatus()}>
              {zh ? "重试读取状态" : "Retry status check"}
            </TmButton>
          ) : null}
        </div>

        {msg ? (
          <p
            role={msg.kind === "err" ? "alert" : "status"}
            className={`font-tm-mono text-xs [overflow-wrap:anywhere] ${msg.kind === "ok" ? "text-tm-pos" : "text-tm-neg"}`}
          >
            {msg.text}
          </p>
        ) : null}
      </div>
    </TmPane>
  );
}
