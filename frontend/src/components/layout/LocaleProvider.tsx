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
        setLocaleToStorage(next);
        return next;
      });
    },
    []
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
