// frontend/src/app/(auth)/signin/error/page.tsx
"use client";
//
// Phase 4b: read the NextAuth ?error= query param and show the real
// reason instead of a generic "link invalid" message. This page now uses
// useSearchParams, so the rendering component MUST be wrapped in
// <Suspense>: without it, next build fails the static-prerender pass
// (the same CSR-bailout class as the M5 E1 Suspense fix).
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { t, getLocaleFromStorage, type Locale, type TranslationKey } from "@/lib/i18n";

// NextAuth v5 error codes -> i18n keys (added in E1).
function errorKeyFor(code: string | null): TranslationKey {
  switch (code) {
    case "CredentialsSignin":
      return "signin.error_credentials";
    case "OAuthAccountNotLinked":
      return "signin.error_oauth_not_linked";
    case "Configuration":
      return "signin.error_configuration";
    case "Verification":
      return "signin.error_verification";
    default:
      return "signin.error_default";
  }
}

function SignInError() {
  const [locale, setLocale] = useState<Locale>("zh");
  const params = useSearchParams();
  const code = params.get("error");

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6 text-center">
      <h1 className="mb-2 text-lg font-semibold text-tm-neg">
        {t(locale, "signin.error_title")}
      </h1>
      <p className="mb-4 text-sm text-tm-muted">
        {t(locale, errorKeyFor(code))}
      </p>
      <Link href="/signin" className="text-sm text-tm-accent hover:underline">
        {t(locale, "signin.back_to_signin")}
      </Link>
    </div>
  );
}

export default function SignInErrorPage() {
  return (
    <Suspense fallback={null}>
      <SignInError />
    </Suspense>
  );
}
