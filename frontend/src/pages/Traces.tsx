import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useRecentIds } from "../lib/recent";
import { Card, Button, Input, Badge, LoadingBlock, ErrorBlock, EmptyBlock, Mono } from "../components/ui";
import { Search, RotateCcw } from "lucide-react";

export default function Traces() {
  const api = useApi();
  const qc = useQueryClient();
  const { ids, add } = useRecentIds("traces");
  const [traceId, setTraceId] = useState("");
  const [active, setActive] = useState<string | null>(null);

  const trace = useQuery({
    queryKey: ["trace", active],
    queryFn: () => api.getTrace(active!),
    enabled: !!active,
  });

  function lookup(id: string) {
    if (!id) return;
    setActive(id);
    add(id);
  }

  const rollback = useMutation({
    mutationFn: () => api.rollbackRun(active!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trace", active] }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Traces</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Full reasoning-chain audit trail for one trace_id — every agent action, timestamped, in
          order.
        </p>
      </div>

      <Card>
        <div className="flex items-end gap-2">
          <div className="flex-1 max-w-md">
            <label className="mb-1 block text-xs text-zinc-500">trace_id</label>
            <Input value={traceId} onChange={setTraceId} placeholder="a1b2c3..." className="w-full" />
          </div>
          <Button variant="primary" disabled={!traceId} onClick={() => lookup(traceId)}>
            <Search className="h-3.5 w-3.5" /> Look up
          </Button>
        </div>
        {ids.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            <span className="text-xs text-zinc-600">recent:</span>
            {ids.slice(0, 8).map((id) => (
              <button
                key={id}
                onClick={() => {
                  setTraceId(id);
                  lookup(id);
                }}
                className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-zinc-400 hover:bg-zinc-700"
              >
                {id.slice(0, 10)}…
              </button>
            ))}
          </div>
        )}
      </Card>

      {active && (
        <Card
          title={<Mono>{active}</Mono>}
          actions={
            <Button size="sm" disabled={rollback.isPending} onClick={() => rollback.mutate()}>
              <RotateCcw className="h-3.5 w-3.5" />
              {rollback.isPending ? "Rolling back…" : "Rollback"}
            </Button>
          }
        >
          {trace.isLoading && <LoadingBlock />}
          {trace.isError && <ErrorBlock message={(trace.error as Error).message} />}
          {rollback.isSuccess && (
            <div className="mb-3 text-xs text-emerald-400">
              {rollback.data.reverted.length} compensating action(s) reverted.
            </div>
          )}
          {rollback.isError && <ErrorBlock message={(rollback.error as ApiError).message} />}
          {trace.data && trace.data.entries.length === 0 && <EmptyBlock label="No activity found for this trace." />}
          {trace.data && trace.data.entries.length > 0 && (
            <ol className="space-y-3 border-l border-zinc-800 pl-4">
              {trace.data.entries.map((e) => (
                <li key={e.entry_id} className="relative">
                  <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-indigo-500" />
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge tone="blue">{e.agent_name}</Badge>
                    <span className="font-medium text-zinc-200">{e.event}</span>
                    <span className="text-zinc-600">{e.ts}</span>
                  </div>
                  <p className="mt-1 text-sm text-zinc-400">{e.detail}</p>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}
    </div>
  );
}
