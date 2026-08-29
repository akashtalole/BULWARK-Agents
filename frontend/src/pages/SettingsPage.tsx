import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSettings } from "../lib/settings";
import { useApi } from "../lib/api";
import { Card, Button, Input, Badge, ErrorBlock } from "../components/ui";

export default function SettingsPage() {
  const { baseUrl, apiKey, setBaseUrl, setApiKey } = useSettings();
  const [baseUrlDraft, setBaseUrlDraft] = useState(baseUrl);
  const [apiKeyDraft, setApiKeyDraft] = useState(apiKey);
  const api = useApi();

  const health = useQuery({
    queryKey: ["status-check", baseUrl, apiKey],
    queryFn: () => api.getStatus(),
    retry: false,
  });

  const registry = useQuery({
    queryKey: ["registry-check", baseUrl, apiKey],
    queryFn: () => api.listRegistry(),
    retry: false,
  });

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Connection</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Point this dashboard at a running BULWARK Agent Gateway. Stored locally in your
          browser only.
        </p>
      </div>

      <Card>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-zinc-500">
              Base URL
            </label>
            <Input value={baseUrlDraft} onChange={setBaseUrlDraft} placeholder="http://localhost:8080" className="w-full" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-zinc-500">
              X-API-Key
            </label>
            <Input value={apiKeyDraft} onChange={setApiKeyDraft} placeholder="demo-key" className="w-full" />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              onClick={() => {
                setBaseUrl(baseUrlDraft.replace(/\/$/, ""));
                setApiKey(apiKeyDraft);
              }}
            >
              Save & reconnect
            </Button>
            {health.isSuccess && <Badge tone="green">Reachable</Badge>}
            {health.isError && <Badge tone="red">Unreachable</Badge>}
          </div>
        </div>
      </Card>

      <Card title="Diagnostics">
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">GET /status</span>
            {health.isLoading && <span className="text-zinc-600">checking…</span>}
            {health.isSuccess && <Badge tone="green">{health.data.status}</Badge>}
            {health.isError && <Badge tone="red">failed</Badge>}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">GET /registry (needs API key)</span>
            {registry.isLoading && <span className="text-zinc-600">checking…</span>}
            {registry.isSuccess && <Badge tone="green">{registry.data.length} agents</Badge>}
            {registry.isError && <Badge tone="red">failed</Badge>}
          </div>
          {registry.isError && (
            <ErrorBlock message={(registry.error as Error).message} />
          )}
        </div>
      </Card>

      <p className="text-xs text-zinc-600">
        If the Agent Gateway is running elsewhere (Cloud Run), make sure its{" "}
        <code className="rounded bg-zinc-800 px-1 py-0.5">BULWARK_CORS_ALLOW_ORIGINS</code>{" "}
        includes this page's origin.
      </p>
    </div>
  );
}
