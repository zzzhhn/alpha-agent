"use client";

import { useSession, signIn, signOut } from "next-auth/react";
import { LogIn, LogOut, UserCircle } from "lucide-react";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

export default function SidebarAuthSlot() {
  const { data: session, status } = useSession();
  const { locale } = useLocale();

  if (status === "loading") {
    return (
      <div className="border-t border-tm-rule p-3 text-[10.5px] text-tm-muted">
        …
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="border-t border-tm-rule p-3">
        <button
          type="button"
          onClick={() => signIn()}
          className="flex w-full items-center gap-2 px-1.5 py-1 text-[11.5px] text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
        >
          <LogIn aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
          {t(locale, "auth.sign_in")}
        </button>
      </div>
    );
  }

  const email = session.user.email ?? "user";
  return (
    <div className="border-t border-tm-rule p-3 space-y-1">
      <div className="flex items-center gap-2 px-1.5 text-[10.5px] text-tm-muted">
        <UserCircle aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span className="truncate">{email}</span>
      </div>
      <button
        type="button"
        onClick={() => signOut({ callbackUrl: "/picks" })}
        className="flex w-full items-center gap-2 px-1.5 py-1 text-[11.5px] text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
      >
        <LogOut aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        {t(locale, "auth.sign_out")}
      </button>
    </div>
  );
}
