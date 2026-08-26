import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const BASE_URL_KEY = "bulwark.baseUrl";
const API_KEY_KEY = "bulwark.apiKey";
const AUTHENTICATED_KEY = "bulwark.authenticated";

// Three ways this resolves, in order:
// 1. VITE_DEFAULT_BASE_URL, baked in at build time by deploy/deploy_frontend.sh
//    (see vite-env.d.ts) -- a GCS-hosted dashboard defaults to its own,
//    separately-deployed Cloud Run backend instead of localhost.
// 2. "" (same-origin/relative fetches), for a production build with no
//    override -- this is the fullstack-on-Cloud-Run case, where the
//    Dockerfile bakes this exact build into the same image and process
//    that serves the API, so the dashboard's own backend is always
//    "wherever this page came from." See main.py's StaticFiles mount.
// 3. localhost:8080, only in `npm run dev` (import.meta.env.DEV), where
//    the dashboard and a locally-running backend are two separate processes.
const DEFAULT_BASE_URL =
  import.meta.env.VITE_DEFAULT_BASE_URL || (import.meta.env.DEV ? "http://localhost:8080" : "");
const DEFAULT_API_KEY = "demo-key";

interface SettingsContextValue {
  baseUrl: string;
  apiKey: string;
  authenticated: boolean;
  setBaseUrl: (v: string) => void;
  setApiKey: (v: string) => void;
  setAuthenticated: (v: boolean) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [baseUrl, setBaseUrlState] = useState(
    () => localStorage.getItem(BASE_URL_KEY) || DEFAULT_BASE_URL,
  );
  const [apiKey, setApiKeyState] = useState(
    () => localStorage.getItem(API_KEY_KEY) || DEFAULT_API_KEY,
  );
  const [authenticated, setAuthenticatedState] = useState(
    () => localStorage.getItem(AUTHENTICATED_KEY) === "true",
  );

  useEffect(() => {
    localStorage.setItem(BASE_URL_KEY, baseUrl);
  }, [baseUrl]);

  useEffect(() => {
    localStorage.setItem(API_KEY_KEY, apiKey);
  }, [apiKey]);

  useEffect(() => {
    localStorage.setItem(AUTHENTICATED_KEY, String(authenticated));
  }, [authenticated]);

  const value = useMemo(
    () => ({
      baseUrl,
      apiKey,
      authenticated,
      setBaseUrl: setBaseUrlState,
      setApiKey: setApiKeyState,
      setAuthenticated: setAuthenticatedState,
    }),
    [baseUrl, apiKey, authenticated],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
