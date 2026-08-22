import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../lib/api";
import {
  Card,
  StatTile,
  Badge,
  Button,
  LoadingBlock,
  ErrorBlock,
  Table,
  Th,
  Td,
  Tr,
} from "../components/ui";
import { PauseCircle, PlayCircle } from "lucide-react";

const AUTONOMY_LABELS = ["L0 · Observe", "L1 · Draft", "L2 · Act w/ approval", "L3 · Autonomous"];

export default function Dashboard() {
  const api = useApi();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const health = useQuery({ queryKey: ["fleet-health"], queryFn: () => api.getFleetHealth() });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => api.getMetrics() });

  async function setAutonomy(level: number) {
    setBusy("autonomy");
    try {
      await api.updateFleetConfig({ autonomy_level: level });
      await qc.invalidateQueries({ queryKey: ["fleet-health"] });
    } finally {
      setBusy(null);
    }
  }

  async function togglePause(agentId: string, paused: boolean) {
    setBusy(agentId);
    try {
      if (paused) await api.updateFleetConfig({ resume_agent_id: agentId });
      else await api.updateFleetConfig({ pause_agent_id: agentId });
      await qc.invalidateQueries({ queryKey: ["fleet-health"] });
    } finally {
      setBusy(null);
    }
  }

  if (health.isLoading || metrics.isLoading) return <LoadingBlock label="Loading fleet state…" />;
  if (health.isError) return <ErrorBlock message={(health.error as Error).message} />;
  if (metrics.isError) return <ErrorBlock message={(metrics.error as Error).message} />;

  const h = health.data!;
  const m = metrics.data!;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Fleet Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Live state of all {h.agents.length} agents — autonomy ladder, spend, and the metrics
          section 13 asks for.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <StatTile
          label="Blind window (avg)"
          value={m.blind_window_avg_days ?? "—"}
          hint="days since last assessment"
        />
        <StatTile label="Vendors" value={m.vendor_count} />
        <StatTile
          label="Questions auto-answered"
          value={`${m.questions_auto_answered_pct}%`}
          tone={m.questions_auto_answered_pct >= 50 ? "good" : "warn"}
        />
        <StatTile
          label="Findings traceable"
          value={`${m.findings_traceable_to_evidence_pct}%`}
          tone="good"
        />
        <StatTile
          label="Fresh control coverage"
          value={`${m.control_coverage_fresh_evidence_pct}%`}
        />
        <StatTile
          label="Injection attempts blocked"
          value={m.injection_attempts_blocked}
          tone={m.injection_attempts_blocked > 0 ? "warn" : "default"}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card
          title="Autonomy ladder / kill switch"
          subtitle="POST /fleet-config — takes effect on every agent's very next tool call"
          className="lg:col-span-1"
        >
          <div className="space-y-2">
            {AUTONOMY_LABELS.map((label, level) => (
              <button
                key={level}
                disabled={busy === "autonomy"}
                onClick={() => setAutonomy(level)}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50 ${
                  h.global_autonomy_level === level
                    ? "border-indigo-500 bg-indigo-500/10 text-indigo-300"
                    : "border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900"
                }`}
              >
                {label}
                {h.global_autonomy_level === level && <Badge tone="blue">active</Badge>}
              </button>
            ))}
          </div>
        </Card>

        <Card
          title="Spend (circuit breaker)"
          subtitle={`Cap: $${h.spend_cap_usd.toFixed(2)}/day`}
          className="lg:col-span-1"
        >
          <div className="space-y-3">
            <StatTile
              label="Today's spend"
              value={`$${Number(h.spend_today.usd ?? 0).toFixed(4)}`}
              tone={Number(h.spend_today.usd ?? 0) >= h.spend_cap_usd ? "bad" : "good"}
            />
            <div className="grid grid-cols-2 gap-2 text-xs text-zinc-500">
              <div>Tokens in: {Number(h.spend_today.tokens_in ?? 0).toLocaleString()}</div>
              <div>Tokens out: {Number(h.spend_today.tokens_out ?? 0).toLocaleString()}</div>
            </div>
            <div className="pt-1">
              <div className="text-xs text-zinc-500">DLQ depth</div>
              <div className={`text-lg font-semibold ${h.dlq_depth > 0 ? "text-amber-400" : "text-zinc-100"}`}>
                {h.dlq_depth}
              </div>
            </div>
          </div>
        </Card>

        <Card
          title="Human review"
          subtitle="Mandatory HITL gates (section 6.4)"
          className="lg:col-span-1"
        >
          <StatTile
            label="Findings requiring human review"
            value={m.findings_requiring_human_review}
            tone={m.findings_requiring_human_review > 0 ? "warn" : "good"}
          />
          <p className="mt-3 text-xs text-zinc-500">{m.note}</p>
        </Card>
      </div>

      <Card
        title="Per-agent effective ceiling"
        subtitle="min(own registered ceiling, global autonomy level) — 0 if individually paused"
      >
        <Table>
          <thead>
            <tr>
              <Th>Agent</Th>
              <Th>Trust zone</Th>
              <Th>Ceiling</Th>
              <Th>Effective</Th>
              <Th>Status</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {h.agents.map((a) => (
              <Tr key={a.agent_id}>
                <Td className="font-medium text-zinc-100">{a.agent_id}</Td>
                <Td>
                  <Badge>{a.trust_zone}</Badge>
                </Td>
                <Td>L{a.autonomy_ceiling}</Td>
                <Td>
                  <Badge tone={a.effective_ceiling === 0 ? "red" : "green"}>L{a.effective_ceiling}</Badge>
                </Td>
                <Td>{a.paused ? <Badge tone="red">paused</Badge> : <Badge tone="green">active</Badge>}</Td>
                <Td>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy === a.agent_id}
                    onClick={() => togglePause(a.agent_id, a.paused)}
                  >
                    {a.paused ? (
                      <>
                        <PlayCircle className="h-3.5 w-3.5" /> Resume
                      </>
                    ) : (
                      <>
                        <PauseCircle className="h-3.5 w-3.5" /> Pause
                      </>
                    )}
                  </Button>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
