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
}

export function LocaleProvider({ children }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>("zh");

  useEffect(() => {
    setLocaleState(getLocaleFromStorage());
  }, []);

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
