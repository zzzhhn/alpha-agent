"use client";

import { useSession, signIn, signOut } from "next-auth/react";
import { LogIn, LogOut, UserCircle } from "lucide-react";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";
import { TmRowButton } from "@/components/tm/TmButton";

export default function SidebarAuthSlot({ compact = false }: { readonly compact?: boolean }) {
  const { data: session, status } = useSession();
  const { locale } = useLocale();

  if (status === "loading") {
    return (
      <div className="border-t border-tm-rule p-3 text-xs text-tm-muted">
        …
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className={compact ? "border-t border-tm-rule py-2" : "border-t border-tm-rule p-3"}>
        <TmRowButton
          onClick={() => signIn()}
          aria-label={compact ? t(locale, "auth.sign_in") : undefined}
          title={compact ? t(locale, "auth.sign_in") : undefined}
          className={compact
            ? "flex h-8 w-full items-center justify-center text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
            : "flex w-full items-center gap-2 px-1.5 py-1 text-xs text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"}
        >
          <LogIn aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
          {compact ? null : t(locale, "auth.sign_in")}
        </TmRowButton>
      </div>
    );
  }

  const email = session.user.email ?? "user";
  if (compact) {
    return (
      <div className="border-t border-tm-rule py-2">
        <TmRowButton
          onClick={() => signOut({ callbackUrl: "/picks" })}
          aria-label={`${t(locale, "auth.sign_out")} ${email}`}
          title={`${email} · ${t(locale, "auth.sign_out")}`}
          className="flex h-8 w-full items-center justify-center text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
        >
          <LogOut aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        </TmRowButton>
      </div>
    );
  }
  return (
    <div className="border-t border-tm-rule p-3 space-y-1">
      <div className="flex items-center gap-2 px-1.5 text-xs text-tm-muted">
        <UserCircle aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span className="truncate">{email}</span>
      </div>
      <TmRowButton
        onClick={() => signOut({ callbackUrl: "/picks" })}
        className="flex w-full items-center gap-2 px-1.5 py-1 text-xs text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
      >
        <LogOut aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        {t(locale, "auth.sign_out")}
      </TmRowButton>
    </div>
  );
}
