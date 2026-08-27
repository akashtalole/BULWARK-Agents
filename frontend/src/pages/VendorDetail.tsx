import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import {
  Card,
  Table,
  Th,
  Td,
  Tr,
  Badge,
  Button,
  Input,
  LoadingBlock,
  ErrorBlock,
  EmptyBlock,
  Mono,
  toneForTier,
  toneForFindingStatus,
  toneForRisk,
} from "../components/ui";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { ArrowLeft } from "lucide-react";

const TABS = [
  "Findings",
  "Contract terms",
  "Subprocessors",
  "Assessment history",
  "Crosswalk",
  "Offboarding",
] as const;
type Tab = (typeof TABS)[number];

export default function VendorDetail() {
  const { vendorId } = useParams<{ vendorId: string }>();
  const api = useApi();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("Findings");

  const vendor = useQuery({
    queryKey: ["vendor", vendorId],
    queryFn: () => api.getVendor(vendorId!),
    enabled: !!vendorId,
  });

  const assess = useMutation({
    mutationFn: () => api.triggerAssessment(vendorId!, "reviewer requested a re-check"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", vendorId] }),
  });

  if (vendor.isLoading) return <LoadingBlock label="Loading vendor…" />;
  if (vendor.isError) return <ErrorBlock message={(vendor.error as Error).message} />;
  const v = vendor.data!;

  return (
    <div className="space-y-6">
      <Link to="/vendors" className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300">
        <ArrowLeft className="h-3 w-3" /> Back to vendors
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-100">{v.name}</h1>
            <Badge tone={toneForTier(v.tier)}>{v.tier}</Badge>
            <Badge>{v.status}</Badge>
          </div>
          <Mono className="mt-1">{v.vendor_id}</Mono>
          <div className="mt-2 flex gap-4 text-xs text-zinc-500">
            <span>
              Blind window:{" "}
              <span className={v.blind_window_days && v.blind_window_days > 30 ? "text-amber-400" : "text-zinc-300"}>
                {v.blind_window_days ?? "—"}d
              </span>
            </span>
            <span>Last assessed: {v.last_assessed_at ?? "never"}</span>
          </div>
        </div>
        <Button variant="primary" disabled={assess.isPending} onClick={() => assess.mutate()}>
          {assess.isPending ? "Triggering…" : "Trigger assessment"}
        </Button>
      </div>
      {assess.isError && <ErrorBlock message={(assess.error as ApiError).message} />}
      {assess.isSuccess && (
        <div className="text-xs text-zinc-500">
          Requested — <Link to="/traces" className="text-indigo-400 hover:underline">trace {assess.data.trace_id}</Link>
        </div>
      )}

      <div className="flex flex-wrap gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-3 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-indigo-500 text-indigo-300"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Findings" && <FindingsTab vendorId={v.vendor_id} />}
      {tab === "Contract terms" && <ContractTermsTab vendorId={v.vendor_id} vendorName={v.name} />}
      {tab === "Subprocessors" && <SubprocessorsTab vendorId={v.vendor_id} vendorName={v.name} />}
      {tab === "Assessment history" && <AssessmentHistoryTab vendorId={v.vendor_id} />}
      {tab === "Crosswalk" && <CrosswalkTab vendorId={v.vendor_id} />}
      {tab === "Offboarding" && <OffboardingTab vendorId={v.vendor_id} />}
    </div>
  );
}

function FindingsTab({ vendorId }: { vendorId: string }) {
  const api = useApi();
  const findings = useQuery({ queryKey: ["vendor-findings", vendorId], queryFn: () => api.getVendorFindings(vendorId) });
  if (findings.isLoading) return <LoadingBlock />;
  if (findings.isError) return <ErrorBlock message={(findings.error as Error).message} />;
  if (findings.data!.length === 0) return <EmptyBlock label="No findings yet for this vendor." />;
  return (
    <Card>
      <Table>
        <thead>
          <tr>
            <Th>Control</Th>
            <Th>Status</Th>
            <Th>Residual risk</Th>
            <Th>Requires human</Th>
            <Th>Gap description</Th>
          </tr>
        </thead>
        <tbody>
          {findings.data!.map((f) => (
            <Tr key={f.finding_id}>
              <Td className="font-medium text-zinc-100">
                <Link to={`/findings?highlight=${f.finding_id}`} className="hover:text-indigo-400">
                  {f.control_ref}
                </Link>
              </Td>
              <Td>
                <Badge tone={toneForFindingStatus(f.status)}>{f.status}</Badge>
              </Td>
              <Td>{f.residual_risk}/25</Td>
              <Td>{f.requires_human ? <Badge tone="amber">yes</Badge> : "no"}</Td>
              <Td className="max-w-md text-zinc-400">{f.gap_description || "—"}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function ContractTermsTab({ vendorId, vendorName }: { vendorId: string; vendorName: string }) {
  const api = useApi();
  const navigate = useNavigate();
  const terms = useQuery({ queryKey: ["vendor-terms", vendorId], queryFn: () => api.getVendorContractTerms(vendorId) });
  if (terms.isLoading) return <LoadingBlock />;
  if (terms.isError) return <ErrorBlock message={(terms.error as Error).message} />;
  if (terms.data!.length === 0)
    return (
      <EmptyBlock label="No contract terms extracted yet — this vendor has no DPA/MSA on file.">
        <Button
          variant="ghost"
          onClick={() => navigate(`/vendors?submit=1&vendor=${encodeURIComponent(vendorName)}&docType=DPA`)}
        >
          Upload a contract for {vendorName}
        </Button>
      </EmptyBlock>
    );
  return (
    <Card>
      <Table>
        <thead>
          <tr>
            <Th>Clause</Th>
            <Th>Risk</Th>
            <Th>Playbook requirement</Th>
            <Th>Deviation</Th>
          </tr>
        </thead>
        <tbody>
          {terms.data!.map((t) => (
            <Tr key={t.term_id}>
              <Td className="font-medium text-zinc-100">{t.clause_type}</Td>
              <Td>
                <Badge tone={toneForRisk(t.risk_level)}>{t.risk_level}</Badge>
              </Td>
              <Td className="max-w-xs text-zinc-400">{t.playbook_requirement}</Td>
              <Td className="max-w-xs">
                {t.deviation ? (
                  <span className="text-amber-400">{t.deviation}</span>
                ) : (
                  <span className="text-emerald-400">meets requirement</span>
                )}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function SubprocessorsTab({ vendorId, vendorName }: { vendorId: string; vendorName: string }) {
  const api = useApi();
  const navigate = useNavigate();
  const subs = useQuery({ queryKey: ["vendor-subs", vendorId], queryFn: () => api.getVendorSubprocessors(vendorId) });
  if (subs.isLoading) return <LoadingBlock />;
  if (subs.isError) return <ErrorBlock message={(subs.error as Error).message} />;
  if (subs.data!.length === 0)
    return (
      <EmptyBlock label="No subprocessors disclosed yet — none have been extracted from a contract for this vendor.">
        <Button
          variant="ghost"
          onClick={() => navigate(`/vendors?submit=1&vendor=${encodeURIComponent(vendorName)}&docType=DPA`)}
        >
          Upload a contract for {vendorName}
        </Button>
      </EmptyBlock>
    );
  return (
    <Card>
      <Table>
        <thead>
          <tr>
            <Th>Name</Th>
            <Th>Purpose</Th>
            <Th>Location</Th>
          </tr>
        </thead>
        <tbody>
          {subs.data!.map((s) => (
            <Tr key={s.subprocessor_id}>
              <Td className="font-medium text-zinc-100">{s.name}</Td>
              <Td className="text-zinc-400">{s.purpose}</Td>
              <Td className="text-zinc-400">{s.location}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function AssessmentHistoryTab({ vendorId }: { vendorId: string }) {
  const api = useApi();
  const history = useQuery({
    queryKey: ["vendor-history", vendorId],
    queryFn: () => api.getVendorAssessmentHistory(vendorId),
  });
  if (history.isLoading) return <LoadingBlock />;
  if (history.isError) return <ErrorBlock message={(history.error as Error).message} />;
  if (history.data!.length === 0)
    return <EmptyBlock label="No reassessment history yet — this is the append-only trail risk_trend_rising is computed from." />;

  const byControl = new Map<string, typeof history.data>();
  for (const s of history.data!) {
    const arr = byControl.get(s.control_ref) ?? [];
    arr.push(s);
    byControl.set(s.control_ref, arr);
  }

  return (
    <div className="space-y-4">
      {[...byControl.entries()].map(([control, snapshots]) => {
        const chartData = snapshots!
          .slice()
          .sort((a, b) => a.created_at.localeCompare(b.created_at))
          .map((s, i) => ({ index: i + 1, residual_risk: s.residual_risk, created_at: s.created_at }));
        return (
          <Card key={control} title={control} subtitle={`${snapshots!.length} snapshot(s)`}>
            <div className="h-48 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                  <XAxis dataKey="index" stroke="#71717a" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 25]} stroke="#71717a" tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
                    labelStyle={{ color: "#a1a1aa" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="residual_risk"
                    stroke="#818cf8"
                    strokeWidth={2}
                    dot={{ r: 4, fill: "#818cf8" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function CrosswalkTab({ vendorId }: { vendorId: string }) {
  const api = useApi();
  const [framework, setFramework] = useState("ISO27001");
  const crosswalk = useQuery({
    queryKey: ["vendor-crosswalk", vendorId, framework],
    queryFn: () => api.getVendorCrosswalk(vendorId, framework),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {["ISO27001", "NISTCSF"].map((f) => (
          <Button key={f} size="sm" variant={framework === f ? "primary" : "ghost"} onClick={() => setFramework(f)}>
            {f}
          </Button>
        ))}
      </div>
      {crosswalk.isLoading && <LoadingBlock />}
      {crosswalk.isError && <ErrorBlock message={(crosswalk.error as Error).message} />}
      {crosswalk.data && (
        <>
          <Card>
            <div className="flex items-center gap-3">
              <div className="text-3xl font-semibold text-zinc-100">{crosswalk.data.coverage_pct}%</div>
              <div className="text-sm text-zinc-500">
                of {crosswalk.data.target_framework} already satisfied via existing SOC 2 findings
              </div>
            </div>
          </Card>
          <Card title="Covered controls">
            {crosswalk.data.covered_controls.length === 0 ? (
              <EmptyBlock label="None yet." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Target control</Th>
                    <Th>Via SOC 2 control</Th>
                    <Th>Source finding</Th>
                  </tr>
                </thead>
                <tbody>
                  {crosswalk.data.covered_controls.map((c) => (
                    <Tr key={c.target_control}>
                      <Td className="font-medium text-zinc-100">{c.target_control}</Td>
                      <Td>{c.via_soc2_control}</Td>
                      <Td>
                        <Mono>{c.source_finding_id}</Mono>
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
          <Card title="Gap controls" subtitle="still need fresh evidence">
            {crosswalk.data.gap_controls.length === 0 ? (
              <EmptyBlock label="No gaps — fully covered." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Target control</Th>
                    <Th>Via SOC 2 control</Th>
                    <Th>Reason</Th>
                  </tr>
                </thead>
                <tbody>
                  {crosswalk.data.gap_controls.map((c) => (
                    <Tr key={c.target_control}>
                      <Td className="font-medium text-zinc-100">{c.target_control}</Td>
                      <Td>{c.via_soc2_control}</Td>
                      <Td className="text-zinc-400">{c.reason}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function OffboardingTab({ vendorId }: { vendorId: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const [reason, setReason] = useState("contract not renewed");
  const [evidenceNote, setEvidenceNote] = useState("");

  const record = useQuery({
    queryKey: ["vendor-offboarding", vendorId],
    queryFn: () => api.getVendorOffboarding(vendorId),
    retry: false,
  });

  const offboard = useMutation({
    mutationFn: () => api.offboardVendor(vendorId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-offboarding", vendorId] });
      qc.invalidateQueries({ queryKey: ["vendor", vendorId] });
    },
  });

  const confirm = useMutation({
    mutationFn: () => api.confirmDataDeletion(vendorId, evidenceNote),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-offboarding", vendorId] });
      qc.invalidateQueries({ queryKey: ["vendor", vendorId] });
    },
  });

  const hasRecord = record.isSuccess;
  const isOverdue = hasRecord && record.data!.status === "pending" && new Date(record.data!.deadline) < new Date();

  return (
    <div className="space-y-4">
      {!hasRecord && (
        <Card
          title="Start the offboarding clock"
          subtitle="Deterministic, no LLM — computes a data-deletion deadline from the vendor's termination_assistance clause or the playbook default"
        >
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">Reason</label>
              <Input value={reason} onChange={setReason} className="w-72" />
            </div>
            <Button variant="primary" disabled={offboard.isPending} onClick={() => offboard.mutate()}>
              {offboard.isPending ? "Starting…" : "Initiate offboarding"}
            </Button>
          </div>
          {offboard.isError && <ErrorBlock message={(offboard.error as ApiError).message} />}
        </Card>
      )}

      {hasRecord && (
        <Card title="Offboarding record">
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div>
              <div className="text-xs text-zinc-500">Status</div>
              <Badge tone={record.data!.status === "confirmed" ? "green" : isOverdue ? "red" : "amber"}>
                {record.data!.status}
                {isOverdue ? " · overdue" : ""}
              </Badge>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Reason</div>
              <div className="text-zinc-300">{record.data!.reason}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Deadline</div>
              <div className={isOverdue ? "text-rose-400" : "text-zinc-300"}>{record.data!.deadline}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Initiated</div>
              <div className="text-zinc-300">{record.data!.initiated_at}</div>
            </div>
          </div>

          {record.data!.status === "pending" && (
            <div className="mt-4 border-t border-zinc-800 pt-4">
              <label className="mb-1 block text-xs text-zinc-500">Evidence note</label>
              <Input
                value={evidenceNote}
                onChange={setEvidenceNote}
                placeholder="vendor's deletion certificate received and matches DPA data scope"
                className="w-full max-w-lg"
              />
              <div className="mt-2">
                <Button
                  variant="primary"
                  disabled={!evidenceNote || confirm.isPending}
                  onClick={() => confirm.mutate()}
                >
                  {confirm.isPending ? "Confirming…" : "Confirm data deletion"}
                </Button>
              </div>
              {confirm.isError && (
                <div className="mt-2">
                  <ErrorBlock message={(confirm.error as ApiError).message} />
                </div>
              )}
              <p className="mt-2 text-xs text-zinc-600">
                Terminal, not reversible — this certifies a real-world fact (the data is gone).
              </p>
            </div>
          )}

          {record.data!.status === "confirmed" && (
            <div className="mt-4 border-t border-zinc-800 pt-4 text-sm">
              <div className="text-xs text-zinc-500">Confirmed at</div>
              <div className="text-zinc-300">{record.data!.confirmed_at}</div>
              <div className="mt-2 text-xs text-zinc-500">Evidence note</div>
              <div className="text-zinc-300">{record.data!.evidence_note}</div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
