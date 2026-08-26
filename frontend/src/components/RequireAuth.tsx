import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "../lib/api";
import { useSettings } from "../lib/settings";
import { LoadingBlock } from "./ui";

/** Gates the whole app behind /login when the backend has
 * BULWARK_UI_PASSWORD configured. If the backend is unreachable, falls
 * through to children instead of blocking -- Layout's own "Not connected"
 * banner already handles that case, and there's no point hard-locking the
 * UI out over a config check that itself couldn't complete. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const api = useApi();
  const { authenticated } = useSettings();

  const authConfig = useQuery({ queryKey: ["auth-config"], queryFn: () => api.getAuthConfig(), retry: false });

  if (authConfig.isLoading) return <LoadingBlock label="Checking…" />;
  if (authConfig.isSuccess && authConfig.data.login_required && !authenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
