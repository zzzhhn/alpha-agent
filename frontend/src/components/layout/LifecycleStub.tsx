"use client";

import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

interface Props {
  readonly stageLabelKey:
    | "lifecycle.data"
    | "lifecycle.alpha"
    | "lifecycle.signal"
    | "lifecycle.report";
  readonly emoji: string;
}

export function LifecycleStub({ stageLabelKey, emoji }: Props) {
  const { locale } = useLocale();
  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 p-10 text-center">
      <div aria-hidden="true" className="text-5xl">
        {emoji}
      </div>
      <h1 className="text-3xl font-semibold text-[var(--text)]">
        {t(locale, stageLabelKey)}
      </h1>
      <p className="max-w-md text-base text-[var(--muted)]">
        {t(locale, "lifecycle.stub.title")} · {t(locale, "lifecycle.stub.body")}
      </p>
    </main>
  );
}
