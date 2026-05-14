// frontend/src/app/(auth)/register/page.tsx
"use client";
//
// Open registration form: email + password + confirm. Calls the C1
// registerAction (a "use server" action); on ok:true it signs the new
// user straight in via signIn("credentials", ...) and redirects. tm-*
// token styling + getLocaleFromStorage() locale pattern mirror
// signin/page.tsx. No useSearchParams here, so no Suspense wrapper needed.
import { useState, useEffect } from "react";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { registerAction, type RegisterError } from "./actions";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

// Map a RegisterError code to an i18n key (keys defined in C2 Option A).
const ERROR_KEY: Record<RegisterError, Parameters<typeof t>[1]> = {
  invalid: "register.error_invalid",
  rate_limited: "register.error_rate_limited",
  email_taken: "register.error_email_taken",
  server_error: "register.error_server",
};

export default function RegisterPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
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
    fd.set("password", password);
    fd.set("confirmPassword", confirmPassword);

    const result = await registerAction(fd);
    if (!result.ok) {
      setErrorKey(ERROR_KEY[result.error]);
      setSubmitting(false);
      return;
    }
    // Registered: log straight in. signIn handles the redirect to /picks.
    await signIn("credentials", { email, password, callbackUrl: "/picks" });
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "register.title")}
      </h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <label className="block text-xs text-tm-muted">
          {t(locale, "register.email_label")}
        </label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t(locale, "register.email_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        <label className="block text-xs text-tm-muted">
          {t(locale, "register.password_label")}
        </label>
        <input
          type="password"
          required
          minLength={8}
          maxLength={32}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t(locale, "register.password_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        <label className="block text-xs text-tm-muted">
          {t(locale, "register.confirm_label")}
        </label>
        <input
          type="password"
          required
          minLength={8}
          maxLength={32}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          placeholder={t(locale, "register.confirm_placeholder")}
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
          {t(locale, submitting ? "register.submitting" : "register.submit_button")}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-tm-muted">
        {t(locale, "register.have_account")}{" "}
        <Link href="/signin" className="text-tm-accent hover:underline">
          {t(locale, "register.signin_link")}
        </Link>
      </p>
    </div>
  );
}
