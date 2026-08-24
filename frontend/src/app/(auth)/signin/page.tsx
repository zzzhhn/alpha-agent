// frontend/src/app/(auth)/signin/page.tsx
"use client";
//
// Phase 4b: password form + "Sign in with Google" + links to /register and
// /forgot-password. Replaces the magic-link email-only form. SignInForm
// uses useSearchParams (callbackUrl), so it stays wrapped in <Suspense>:
// removing the wrapper would fail the next build static-prerender pass.
import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";

function SignInForm() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") ?? "/picks";

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    // signIn handles the redirect: to callbackUrl on success, to
    // /signin/error?error=CredentialsSignin on a bad password.
    await signIn("credentials", { email, password, callbackUrl });
  };

  const onGoogle = async () => {
    await signIn("google", { callbackUrl });
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "signin.title")}
      </h1>
      <form onSubmit={onPasswordSubmit} className="space-y-3">
        <TmInput
          label={t(locale, "signin.email_label")}
          type="email"
          required
          value={email}
          onChange={setEmail}
          placeholder={t(locale, "signin.email_placeholder")}
        />
        <TmInput
          label={t(locale, "signin.password_label")}
          type="password"
          required
          value={password}
          onChange={setPassword}
          placeholder={t(locale, "signin.password_placeholder")}
        />
        <TmButton
          type="submit"
          loading={submitting}
          loadingLabel={t(locale, "signin.signing_in")}
          className="w-full"
        >
          {t(locale, "signin.signin_button")}
        </TmButton>
      </form>
      <TmButton
        type="button"
        onClick={onGoogle}
        variant="secondary"
        className="mt-3 w-full"
      >
        {t(locale, "signin.google_button")}
      </TmButton>
      <div className="mt-4 flex flex-col gap-1 text-center text-xs text-tm-muted">
        <Link href="/register" className="text-tm-accent hover:underline">
          {t(locale, "signin.register_link")}
        </Link>
        <Link href="/forgot-password" className="text-tm-accent hover:underline">
          {t(locale, "signin.forgot_link")}
        </Link>
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInForm />
    </Suspense>
  );
}
