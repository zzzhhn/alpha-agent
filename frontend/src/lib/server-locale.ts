// Server-only locale resolver. Reads the "locale" cookie that the client
// LocaleProvider writes (via setLocaleToStorage). Defaults to "zh" — the
// app's default locale, matching getLocaleFromStorage's localStorage default
// — so a fresh visitor with no cookie yet gets Chinese SSR rather than an
// English flash. Use this in every server component that renders localized
// text so SSR stays in sync with the client toggle.
import { cookies } from "next/headers";
import type { Locale } from "./i18n";

export async function getServerLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  const v = cookieStore.get("locale")?.value;
  return v === "en" ? "en" : "zh";
}
