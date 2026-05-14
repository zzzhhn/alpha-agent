"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

export default function SignInErrorPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);
  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6 text-center">
      <h1 className="mb-2 text-lg font-semibold text-tm-neg">
        {t(locale, "signin.error_title")}
      </h1>
      <p className="mb-4 text-sm text-tm-muted">{t(locale, "signin.error_body")}</p>
      <Link href="/signin" className="text-sm text-tm-accent hover:underline">
        {t(locale, "signin.back_to_signin")}
      </Link>
    </div>
  );
}
