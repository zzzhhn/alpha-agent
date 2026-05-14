// frontend/src/app/(auth)/reset-password/page.tsx
"use client";
//
// email + 6-digit code + new password form -> D2 resetPasswordAction.
// On success, links the user to /signin to log in with the new password.
// No useSearchParams, so no Suspense wrapper. tm-* token styling.
import { useState, useEffect } from "react";
import Link from "next/link";
import { resetPasswordAction, type ResetError } from "./actions";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

const ERROR_KEY: Record<ResetError, Parameters<typeof t>[1]> = {
  invalid: "reset.error_invalid",
  wrong_code: "reset.error_wrong_code",
  expired_code: "reset.error_expired_code",
  used_code: "reset.error_used_code",
  server_error: "reset.error_server",
};

export default function ResetPasswordPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [errorKey, setErrorKey] = useState<Parameters<typeof t>[1] | null>(null);

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    const fd = new FormData();
    fd.set("email", email);
    fd.set("code", code);
    fd.set("newPassword", newPassword);
    const result = await resetPasswordAction(fd);
    setSubmitting(false);
    if (!result.ok) {
      setErrorKey(ERROR_KEY[result.error]);
      return;
    }
    setDone(true);
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "reset.title")}
      </h1>
      {done ? (
        <p className="text-sm text-tm-muted">
          {t(locale, "reset.done_body")}{" "}
          <Link href="/signin" className="text-tm-accent hover:underline">
            {t(locale, "reset.done_signin_link")}
          </Link>
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-xs text-tm-muted">
            {t(locale, "reset.email_label")}
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t(locale, "reset.email_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          <label className="block text-xs text-tm-muted">
            {t(locale, "reset.code_label")}
          </label>
          <input
            type="text"
            required
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={t(locale, "reset.code_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          <label className="block text-xs text-tm-muted">
            {t(locale, "reset.new_password_label")}
          </label>
          <input
            type="password"
            required
            minLength={8}
            maxLength={32}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={t(locale, "reset.new_password_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          {errorKey && (
            <p className="text-xs text-tm-neg">{t(locale, errorKey)}</p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent disabled:opacity-60"
          >
            {t(locale, submitting ? "reset.submitting" : "reset.submit_button")}
          </button>
        </form>
      )}
      <p className="mt-4 text-center text-xs text-tm-muted">
        <Link href="/forgot-password" className="text-tm-accent hover:underline">
          {t(locale, "reset.need_code_link")}
        </Link>
      </p>
    </div>
  );
}
