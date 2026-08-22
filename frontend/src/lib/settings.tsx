import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const BASE_URL_KEY = "bulwark.baseUrl";
const API_KEY_KEY = "bulwark.apiKey";

const DEFAULT_BASE_URL = "http://localhost:8080";
const DEFAULT_API_KEY = "demo-key";

interface SettingsContextValue {
  baseUrl: string;
  apiKey: string;
  setBaseUrl: (v: string) => void;
  setApiKey: (v: string) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [baseUrl, setBaseUrlState] = useState(
    () => localStorage.getItem(BASE_URL_KEY) || DEFAULT_BASE_URL,
  );
  const [apiKey, setApiKeyState] = useState(
    () => localStorage.getItem(API_KEY_KEY) || DEFAULT_API_KEY,
  );

  useEffect(() => {
    localStorage.setItem(BASE_URL_KEY, baseUrl);
  }, [baseUrl]);

  useEffect(() => {
    localStorage.setItem(API_KEY_KEY, apiKey);
  }, [apiKey]);

  const value = useMemo(
    () => ({
      baseUrl,
      apiKey,
      setBaseUrl: setBaseUrlState,
      setApiKey: setApiKeyState,
    }),
    [baseUrl, apiKey],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
