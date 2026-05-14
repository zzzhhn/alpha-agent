"use client";

import { useEffect, useState } from "react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

export default function CheckEmailPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);
  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6 text-center">
      <h1 className="mb-2 text-lg font-semibold text-tm-fg">
        {t(locale, "signin.check_email_title")}
      </h1>
      <p className="text-sm text-tm-muted">{t(locale, "signin.check_email_body")}</p>
    </div>
  );
}
