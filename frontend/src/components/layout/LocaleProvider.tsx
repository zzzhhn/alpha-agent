"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useRouter } from "next/navigation";
import {
  type Locale,
  getLocaleFromStorage,
  setLocaleToStorage,
} from "@/lib/i18n";

interface LocaleContextValue {
  readonly locale: Locale;
  readonly setLocale: Dispatch<SetStateAction<Locale>>;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: "zh",
  setLocale: () => {},
});

interface LocaleProviderProps {
  readonly children: ReactNode;
  // Server-resolved locale (from the `locale` cookie, read in the dashboard
  // layout via getServerLocale). Seeding useState with this makes the client's
  // first render match the SSR output, eliminating the hydration text mismatch
  // (React #425) and the old router.refresh() self-heal that re-rendered the
  // root (React #422).
  readonly initialLocale: Locale;
}

export function LocaleProvider({ children, initialLocale }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const router = useRouter();

  useEffect(() => {
    // setLocaleToStorage keeps localStorage and the cookie in sync, so in steady
    // state this is a no-op. It only fires for a legacy client whose locale lived
    // in localStorage but not the cookie: update the UI + re-sync the cookie for
    // the next SSR. No router.refresh — initialLocale already matched SSR, so
    // there is nothing to re-render on the server here (this avoids the #422
    // recover-by-client-render thrash).
    const stored = getLocaleFromStorage();
    if (stored !== initialLocale) {
      setLocaleState(stored);
      setLocaleToStorage(stored);
    }
  }, [initialLocale]);

  const setLocale: Dispatch<SetStateAction<Locale>> = useCallback(
    (action) => {
      setLocaleState((prev) => {
        const next = typeof action === "function" ? action(prev) : action;
        if (next !== prev) {
          setLocaleToStorage(next);
          // Re-render server components too. getServerLocale() reads the cookie
          // we just wrote, so SSR-localized text (decision card, mining journal,
          // section headers) follows the toggle live instead of staying frozen
          // in the page-load language until a manual reload. Safe here: this is a
          // deliberate, user-initiated refresh long after hydration — not the
          // #422 hydration self-heal that was removed. initialLocale already
          // matches SSR, so the refreshed tree stays consistent with this state.
          router.refresh();
        }
        return next;
      });
    },
    [router]
  );

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}
