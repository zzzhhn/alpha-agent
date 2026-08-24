// frontend/src/app/(auth)/forgot-password/page.tsx
"use client";
//
// Email-only form -> D1 forgotPasswordAction. Always shows the same
// "if that email exists, a code was sent" confirmation (no enumeration).
// No useSearchParams, so no Suspense wrapper needed. tm-* token styling.
import { useState, useEffect } from "react";
import Link from "next/link";
import { forgotPasswordAction, type ForgotError } from "./actions";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";

const ERROR_KEY: Record<ForgotError, Parameters<typeof t>[1]> = {
  invalid: "forgot.error_invalid",
  rate_limited: "forgot.error_rate_limited",
};

export default function ForgotPasswordPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
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
    const result = await forgotPasswordAction(fd);
    setSubmitting(false);
    if (!result.ok) {
      setErrorKey(ERROR_KEY[result.error]);
      return;
    }
    setSent(true);
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "forgot.title")}
      </h1>
      {sent ? (
        <p className="text-sm text-tm-muted">{t(locale, "forgot.sent_body")}</p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <TmInput
            label={t(locale, "forgot.email_label")}
            type="email"
            required
            value={email}
            onChange={setEmail}
            placeholder={t(locale, "forgot.email_placeholder")}
          />
          {errorKey && (
            <p className="text-xs text-tm-neg">{t(locale, errorKey)}</p>
          )}
          <TmButton
            type="submit"
            loading={submitting}
            loadingLabel={t(locale, "forgot.submitting")}
            className="w-full"
          >
            {t(locale, "forgot.submit_button")}
          </TmButton>
        </form>
      )}
      <p className="mt-4 text-center text-xs text-tm-muted">
        <Link href="/reset-password" className="text-tm-accent hover:underline">
          {t(locale, "forgot.have_code_link")}
        </Link>
        {" / "}
        <Link href="/signin" className="text-tm-accent hover:underline">
          {t(locale, "forgot.back_to_signin")}
        </Link>
      </p>
    </div>
  );
}
