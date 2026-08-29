import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useSort } from "../lib/sort";
import type { Finding } from "../lib/types";
import {
  Card,
  Table,
  Th,
  Td,
  Tr,
  Badge,
  Button,
  Select,
  Input,
  Textarea,
  LoadingBlock,
  ErrorBlock,
  EmptyBlock,
  Mono,
  toneForFindingStatus,
} from "../components/ui";

const STATUS_OPTIONS = ["", "satisfied", "gap", "exception", "unknown"];
const DECISIONS = ["accept_risk", "request_remediation", "reject"];

export default function Findings() {
  const api = useApi();
  const [params] = useSearchParams();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(params.get("highlight"));
  const sort = useSort<Finding>();

  const findings = useQuery({
    queryKey: ["findings", status],
    queryFn: () => api.listFindings(status || undefined),
  });

  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api.listVendors() });
  const vendorNameById = new Map((vendors.data ?? []).map((v) => [v.vendor_id, v.name]));

  const searchLower = search.toLowerCase();
  const rows = findings.data
    ? sort.apply(
        findings.data.filter(
          (f) =>
            f.control_ref.toLowerCase().includes(searchLower) ||
            f.vendor_id.includes(search) ||
            (vendorNameById.get(f.vendor_id) ?? "").toLowerCase().includes(searchLower),
        ),
      )
    : [];

  useEffect(() => {
    const h = params.get("highlight");
    if (h) setSelected(h);
  }, [params]);

  if (findings.isLoading) return <LoadingBlock label="Loading findings…" />;
  if (findings.isError) return <ErrorBlock message={(findings.error as Error).message} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Findings</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Global, filterable — every finding cites the evidence/assertions that justify it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input value={search} onChange={setSearch} placeholder="Search control or vendor…" className="w-56" />
          <Select
            value={status}
            onChange={setStatus}
            options={STATUS_OPTIONS.map((s) => ({ value: s, label: s || "all statuses" }))}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          {rows.length === 0 ? (
            <EmptyBlock label="No findings match this filter." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th onClick={() => sort.toggle("control_ref")} sortDirection={sort.directionFor("control_ref")}>
                    Control
                  </Th>
                  <Th onClick={() => sort.toggle("vendor_id")} sortDirection={sort.directionFor("vendor_id")}>
                    Vendor
                  </Th>
                  <Th onClick={() => sort.toggle("status")} sortDirection={sort.directionFor("status")}>
                    Status
                  </Th>
                  <Th onClick={() => sort.toggle("residual_risk")} sortDirection={sort.directionFor("residual_risk")}>
                    Risk
                  </Th>
                  <Th>Human</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((f) => (
                  <Tr
                    key={f.finding_id}
                    onClick={() => setSelected(f.finding_id)}
                    className={selected === f.finding_id ? "bg-indigo-500/10" : undefined}
                  >
                    <Td className="font-medium text-zinc-100">{f.control_ref}</Td>
                    <Td>
                      <Link
                        to={`/vendors/${f.vendor_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-zinc-200 hover:text-indigo-400"
                      >
                        {vendorNameById.get(f.vendor_id) ?? f.vendor_id}
                      </Link>
                    </Td>
                    <Td>
                      <Badge tone={toneForFindingStatus(f.status)}>{f.status}</Badge>
                    </Td>
                    <Td>{f.residual_risk}/25</Td>
                    <Td>
                      {f.requires_human ? (
                        f.human_decision ? (
                          <Badge tone="green">decided</Badge>
                        ) : (
                          <Badge tone="amber">pending</Badge>
                        )
                      ) : (
                        "—"
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        <div className="xl:col-span-2">
          {selected ? (
            <FindingDetail findingId={selected} vendorNameById={vendorNameById} onDecided={() => findings.refetch()} />
          ) : (
            <Card>
              <EmptyBlock label="Select a finding to see its reasoning chain and record a decision." />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function FindingDetail({
  findingId,
  vendorNameById,
  onDecided,
}: {
  findingId: string;
  vendorNameById: Map<string, string>;
  onDecided: () => void;
}) {
  const api = useApi();
  const qc = useQueryClient();
  const explain = useQuery({ queryKey: ["explain", findingId], queryFn: () => api.explainFinding(findingId) });

  const [actor, setActor] = useState("");
  const [decision, setDecision] = useState(DECISIONS[0]);
  const [rationale, setRationale] = useState("");

  const decide = useMutation({
    mutationFn: () => api.recordFindingDecision(findingId, actor, decision, rationale),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["explain", findingId] });
      onDecided();
      setRationale("");
    },
  });

  if (explain.isLoading) return <LoadingBlock />;
  if (explain.isError) return <ErrorBlock message={(explain.error as Error).message} />;
  const { finding, reasoning } = explain.data!;

  return (
    <div className="space-y-4">
      <Card title={finding.control_ref} subtitle={finding.finding_id}>
        <Link to={`/vendors/${finding.vendor_id}`} className="text-sm text-indigo-400 hover:underline">
          {vendorNameById.get(finding.vendor_id) ?? finding.vendor_id}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge tone={toneForFindingStatus(finding.status)}>{finding.status}</Badge>
          <Badge tone={finding.residual_risk >= 15 ? "red" : "gray"}>risk {finding.residual_risk}/25</Badge>
          {finding.requires_human && <Badge tone="amber">requires human</Badge>}
        </div>
        {finding.gap_description && <p className="mt-3 text-sm text-zinc-400">{finding.gap_description}</p>}
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-zinc-500">
          <div>evidence_ids: {finding.evidence_ids.length}</div>
          <div>assertion_ids: {finding.assertion_ids.length}</div>
        </div>
      </Card>

      <Card title="Reasoning chain" subtitle="why the agent decided this — not just the verdict">
        {reasoning.length === 0 ? (
          <EmptyBlock label="No reasoning record on file." />
        ) : (
          <div className="space-y-4">
            {reasoning.map((r) => (
              <div key={r.decision_id} className="rounded-lg border border-zinc-800 p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-zinc-500">
                  <span>{r.agent}</span>
                  {r.model && <Mono>{r.model}</Mono>}
                </div>
                <div className="space-y-1.5">
                  {r.considered.map((c, i) => (
                    <div
                      key={i}
                      className={`flex items-center justify-between rounded px-2 py-1 text-xs ${
                        c.chosen ? "bg-emerald-500/10 text-emerald-300" : "text-zinc-500"
                      }`}
                    >
                      <span>
                        {c.chosen ? "✓ " : ""}
                        {c.option}
                        {c.why_not && <span className="ml-1 text-zinc-600">— {c.why_not}</span>}
                      </span>
                      <span className="tabular-nums">{c.score.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Record a decision" subtitle="also unblocks Remediation Router's draft_vendor_email">
        {finding.human_decision ? (
          <div className="text-sm">
            <div className="text-zinc-300">
              <span className="font-medium">{finding.human_decision.actor}</span> ·{" "}
              <Badge>{finding.human_decision.decision}</Badge>
            </div>
            <p className="mt-1 text-zinc-500">{finding.human_decision.rationale}</p>
          </div>
        ) : (
          <div className="space-y-2">
            <Input value={actor} onChange={setActor} placeholder="you@company.com" className="w-full" />
            <Select value={decision} onChange={setDecision} options={DECISIONS.map((d) => ({ value: d, label: d }))} />
            <Textarea value={rationale} onChange={setRationale} placeholder="Rationale…" rows={2} />
            <Button
              variant="primary"
              disabled={!actor || !rationale || decide.isPending}
              onClick={() => decide.mutate()}
            >
              {decide.isPending ? "Recording…" : "Record decision"}
            </Button>
            {decide.isError && <ErrorBlock message={(decide.error as ApiError).message} />}
          </div>
        )}
      </Card>
    </div>
  );
}
