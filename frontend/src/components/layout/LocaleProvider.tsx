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
  getLocaleFromDocumentCookie,
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
}

export function LocaleProvider({ children }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>("zh");
  const router = useRouter();

  useEffect(() => {
    const stored = getLocaleFromStorage();
    setLocaleState(stored);
    // Self-heal the SSR locale cookie. Legacy clients persisted locale only
    // to localStorage, so server components rendered with the default (now
    // zh) regardless of the user's real choice. If the cookie disagrees with
    // localStorage, sync it and re-render the server tree once so SSR text
    // matches the toggle. Steady state: cookie already matches → no refresh.
    if (getLocaleFromDocumentCookie() !== stored) {
      setLocaleToStorage(stored);
      router.refresh();
    }
  }, [router]);

  const setLocale: Dispatch<SetStateAction<Locale>> = useCallback(
    (action) => {
      setLocaleState((prev) => {
        const next =
          typeof action === "function" ? action(prev) : action;
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
