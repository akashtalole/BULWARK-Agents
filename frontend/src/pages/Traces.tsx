import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useRecentIds } from "../lib/recent";
import { formatDate } from "../lib/format";
import {
  Card,
  Table,
  Th,
  Td,
  Tr,
  Button,
  Input,
  Select,
  Badge,
  LoadingBlock,
  ErrorBlock,
  EmptyBlock,
  Mono,
} from "../components/ui";
import { Search, RotateCcw } from "lucide-react";

const ALL_VENDORS = "__all__";

export default function Traces() {
  const api = useApi();
  const qc = useQueryClient();
  const { ids, add } = useRecentIds("traces");
  const [searchParams, setSearchParams] = useSearchParams();
  const [traceId, setTraceId] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [vendorFilter, setVendorFilter] = useState(ALL_VENDORS);

  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api.listVendors() });
  const vendorNameById = new Map((vendors.data ?? []).map((v) => [v.vendor_id, v.name]));

  const traces = useQuery({
    queryKey: ["traces", vendorFilter],
    queryFn: () => api.listTraces(vendorFilter === ALL_VENDORS ? undefined : vendorFilter),
  });

  // Deep-linked from a vendor's page (?vendor=<id>) or straight to one
  // trace (?trace=<id>) -- e.g. "Trigger assessment"'s success banner, or
  // a vendor detail page's "View traces" button -- since a raw trace_id
  // is otherwise nowhere a person would ever see it to paste in by hand.
  useEffect(() => {
    const vendorParam = searchParams.get("vendor");
    const traceParam = searchParams.get("trace");
    if (vendorParam) setVendorFilter(vendorParam);
    if (traceParam) lookup(traceParam);
    if (vendorParam || traceParam) setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const trace = useQuery({
    queryKey: ["trace", active],
    queryFn: () => api.getTrace(active!),
    enabled: !!active,
  });

  function lookup(id: string) {
    if (!id) return;
    setActive(id);
    setTraceId(id);
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
          order. Browse recent traces below, or paste a trace_id directly.
        </p>
      </div>

      <Card
        title="Recent traces"
        actions={
          <Select
            value={vendorFilter}
            onChange={setVendorFilter}
            options={[
              { value: ALL_VENDORS, label: "All vendors" },
              { value: "__fleet__", label: "Fleet-wide only" },
              ...(vendors.data ?? []).map((v) => ({ value: v.vendor_id, label: v.name })),
            ]}
          />
        }
      >
        {traces.isLoading && <LoadingBlock />}
        {traces.isError && <ErrorBlock message={(traces.error as Error).message} />}
        {traces.data && traces.data.length === 0 && (
          <EmptyBlock label="No traces yet — submit a vendor artifact or trigger an assessment to generate one." />
        )}
        {traces.data && traces.data.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>Trace</Th>
                <Th>Vendor</Th>
                <Th>Status</Th>
                <Th>Last event</Th>
                <Th>Events</Th>
                <Th>Last activity</Th>
              </tr>
            </thead>
            <tbody>
              {(vendorFilter === "__fleet__" ? traces.data.filter((t) => !t.vendor_id) : traces.data).map((t) => (
                <Tr key={t.trace_id} onClick={() => lookup(t.trace_id)}>
                  <Td>
                    <Mono>{t.trace_id.slice(0, 14)}…</Mono>
                  </Td>
                  <Td className="text-zinc-300">
                    {t.vendor_id ? vendorNameById.get(t.vendor_id) ?? t.vendor_id : <span className="text-zinc-600">fleet-wide</span>}
                  </Td>
                  <Td>
                    <Badge tone={t.status === "completed" ? "green" : "amber"}>{t.status}</Badge>
                  </Td>
                  <Td className="text-zinc-400">{t.last_event}</Td>
                  <Td>{t.event_count}</Td>
                  <Td className="text-zinc-500">{formatDate(t.last_event_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="Look up a trace_id directly">
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
            <span className="text-xs text-zinc-600">recently viewed:</span>
            {ids.slice(0, 8).map((id) => (
              <button
                key={id}
                onClick={() => lookup(id)}
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
