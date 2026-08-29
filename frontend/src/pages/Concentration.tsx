import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { Card, Badge, Button, LoadingBlock, ErrorBlock, EmptyBlock, toneForRisk } from "../components/ui";
import { RefreshCw, Network } from "lucide-react";

export default function Concentration() {
  const api = useApi();
  const qc = useQueryClient();
  const risks = useQuery({ queryKey: ["concentration-risks"], queryFn: () => api.listConcentrationRisks() });
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api.listVendors() });
  const vendorNameById = new Map((vendors.data ?? []).map((v) => [v.vendor_id, v.name]));

  const tick = useMutation({
    mutationFn: () => api.tickConcentrationAnalyzer(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["concentration-risks"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Concentration Risks</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Vendors that look diversified but secretly share a subprocessor — deterministic, no
            LLM call.
          </p>
        </div>
        <Button variant="primary" disabled={tick.isPending} onClick={() => tick.mutate()}>
          <RefreshCw className={`h-3.5 w-3.5 ${tick.isPending ? "animate-spin" : ""}`} />
          {tick.isPending ? "Analyzing…" : "Re-run analysis"}
        </Button>
      </div>
      {tick.isError && <ErrorBlock message={(tick.error as ApiError).message} />}
      {tick.isSuccess && (
        <div className="text-xs text-zinc-500">{tick.data.clusters_detected} cluster(s) detected.</div>
      )}

      {risks.isLoading && <LoadingBlock label="Loading concentration risks…" />}
      {risks.isError && <ErrorBlock message={(risks.error as Error).message} />}
      {risks.data && risks.data.length === 0 && (
        <Card>
          <EmptyBlock label="No shared-subprocessor clusters detected yet." />
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {risks.data?.map((r) => (
          <Card key={r.risk_id}>
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <Network className="h-4 w-4 text-zinc-500" />
                <div className="text-sm font-semibold text-zinc-100">{r.subprocessor_name}</div>
              </div>
              <Badge tone={toneForRisk(r.severity)}>{r.severity}</Badge>
            </div>
            <p className="mt-3 text-sm text-zinc-400">{r.detail}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge tone="red">{r.critical_vendor_count} critical-tier</Badge>
              <Badge>{r.vendor_ids.length} vendors total</Badge>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {r.vendor_ids.map((v) => (
                <Link
                  key={v}
                  to={`/vendors/${v}`}
                  className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700 hover:text-indigo-400"
                >
                  {vendorNameById.get(v) ?? v}
                </Link>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
