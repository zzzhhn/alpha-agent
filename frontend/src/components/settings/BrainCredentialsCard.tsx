"use client";

import { useEffect, useState } from "react";
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
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState<Busy>("idle");
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  useEffect(() => {
    fetchBrainStatus()
      .then(setStatus)
      .catch(() => setStatus({ connected: false }));
  }, []);

  async function onSave() {
    if (!username.trim() || !password) {
      setMsg({ kind: "err", text: zh ? "用户名和密码都要填" : "username and password required" });
      return;
    }
    setBusy("saving");
    setMsg(null);
    try {
      const r = await saveBrainCredentials(username.trim(), password);
      setStatus({ connected: true, username_last4: r.username_last4 });
      setPassword("");
      setMsg({ kind: "ok", text: zh ? "已加密保存" : "saved (encrypted)" });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy("idle");
    }
  }

  async function onTest() {
    setBusy("testing");
    setMsg(null);
    try {
      const r = await testBrainConnection();
      setMsg(
        r.ok
          ? { kind: "ok", text: zh ? "连接成功" : "connection ok" }
          : { kind: "err", text: (zh ? "连接失败: " : "connection failed: ") + (r.error ?? "") },
      );
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy("idle");
    }
  }

  const meta = status?.connected
    ? (zh ? `已连接 · …${status.username_last4}` : `connected · …${status.username_last4}`)
    : zh
      ? "未连接"
      : "not connected";

  return (
    <TmPane title="WORLDQUANT.BRAIN" meta={meta}>
      <div className="flex flex-col gap-3 px-3 py-3">
        <p className="font-tm-mono text-xs leading-relaxed text-tm-muted">
          {zh
            ? "填入你的 WorldQuant BRAIN 登录。加密存储,仅在服务端用于挖矿仿真,明文永不回传。建议用专用/受限账号。"
            : "Your WorldQuant BRAIN login. Stored encrypted, used server-side only for mining simulations; plaintext is never returned. A dedicated/limited account is recommended."}
        </p>

        <TmInput
          label={zh ? "BRAIN 用户名 / 邮箱" : "BRAIN USERNAME / EMAIL"}
          fieldSize="sm"
          value={username}
          onChange={setUsername}
          placeholder={zh ? "你的 BRAIN 登录邮箱" : "your BRAIN login email"}
          autoComplete="off"
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
            />
            <TmButton
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setReveal((r) => !r)}
            >
              {reveal ? (zh ? "隐藏" : "HIDE") : zh ? "显示" : "REVEAL"}
            </TmButton>
          </div>
        </TmFieldShell>

        <div className="flex gap-2">
          <TmButton
            onClick={onSave}
            disabled={busy !== "idle"}
            loading={busy === "saving"}
            loadingLabel={zh ? "保存中…" : "Saving…"}
          >
            {zh ? "保存" : "Save"}
          </TmButton>
          {status?.connected ? (
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
        </div>

        {msg ? (
          <p
            className={`font-tm-mono text-xs ${msg.kind === "ok" ? "text-tm-pos" : "text-tm-neg"}`}
          >
            {msg.text}
          </p>
        ) : null}
      </div>
    </TmPane>
  );
}
