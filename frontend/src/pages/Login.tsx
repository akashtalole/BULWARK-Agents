import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useSettings } from "../lib/settings";
import { Card, Button, Input, ErrorBlock, LoadingBlock } from "../components/ui";

export default function Login() {
  const api = useApi();
  const navigate = useNavigate();
  const { setApiKey, setAuthenticated } = useSettings();
  const [password, setPassword] = useState("");

  const authConfig = useQuery({ queryKey: ["auth-config"], queryFn: () => api.getAuthConfig(), retry: false });

  const login = useMutation({
    mutationFn: () => api.login(password),
    onSuccess: (result) => {
      setApiKey(result.api_key);
      setAuthenticated(true);
      navigate("/", { replace: true });
    },
  });

  if (authConfig.isLoading) return <LoadingBlock label="Checking…" />;
  // Backend has no password configured -- nothing to log in to, so this
  // page has no reason to exist right now. Fall through to the dashboard,
  // which handles an unreachable/misconfigured backend on its own.
  if (authConfig.isSuccess && !authConfig.data.login_required) return <Navigate to="/" replace />;

  return (
    <div className="flex h-screen w-full items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-base font-bold text-white">
            B
          </div>
          <div>
            <div className="text-sm font-semibold text-zinc-100">BULWARK</div>
            <div className="text-[11px] text-zinc-500">Assurance Fleet</div>
          </div>
        </div>

        <Card>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate();
            }}
          >
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-zinc-500">
                Password
              </label>
              <Input
                type="password"
                value={password}
                onChange={setPassword}
                placeholder="••••••••"
                className="w-full"
              />
            </div>
            <Button type="submit" variant="primary" className="w-full justify-center" disabled={login.isPending || !password}>
              {login.isPending ? "Signing in…" : "Sign in"}
            </Button>
            {login.isError && (
              <ErrorBlock
                message={
                  (login.error as ApiError).status === 401
                    ? "Incorrect password."
                    : (login.error as Error).message
                }
              />
            )}
          </form>
        </Card>

        {authConfig.isError && (
          <p className="text-center text-xs text-zinc-600">
            Can't reach the Agent Gateway to check whether a password is required. Open{" "}
            <span className="text-zinc-500">Connection settings</span> once you're in, or confirm the backend is
            running.
          </p>
        )}
      </div>
    </div>
  );
}
