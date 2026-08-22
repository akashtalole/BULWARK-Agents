import { useQuery } from "@tanstack/react-query";
import { useApi } from "../lib/api";
import { Card, Badge, LoadingBlock, ErrorBlock, Mono } from "../components/ui";

function modelTone(model: string): "purple" | "blue" | "gray" {
  if (model.toLowerCase().includes("deterministic")) return "gray";
  if (model.toLowerCase().includes("pro")) return "purple";
  return "blue";
}

export default function Agents() {
  const api = useApi();
  const registry = useQuery({ queryKey: ["registry"], queryFn: () => api.listRegistry() });
  const health = useQuery({ queryKey: ["fleet-health"], queryFn: () => api.getFleetHealth() });

  if (registry.isLoading) return <LoadingBlock label="Loading agent registry…" />;
  if (registry.isError) return <ErrorBlock message={(registry.error as Error).message} />;

  const pausedIds = new Set((health.data?.agents ?? []).filter((a) => a.paused).map((a) => a.agent_id));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Agent Registry</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every agent self-registers here at startup — GET /registry, live at{" "}
          {registry.data!.length} agents.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {registry.data!.map((a) => (
          <Card key={a.agent_id}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-zinc-100">{a.name}</div>
                <Mono className="mt-0.5">{a.agent_id}</Mono>
              </div>
              {pausedIds.has(a.agent_id) && <Badge tone="red">paused</Badge>}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-zinc-400">{a.description}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge tone={modelTone(a.model)}>{a.model}</Badge>
              <Badge>{a.trust_zone}</Badge>
              <Badge tone="blue">L{a.autonomy_ceiling} ceiling</Badge>
            </div>
            {a.departments.length > 0 && (
              <div className="mt-3">
                <div className="text-[10px] font-medium uppercase tracking-wide text-zinc-600">
                  Departments
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {a.departments.map((d) => (
                    <span key={d} className="text-xs text-zinc-500">
                      {d}
                      {d !== a.departments[a.departments.length - 1] ? " ·" : ""}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {a.tools.length > 0 && (
              <div className="mt-3">
                <div className="text-[10px] font-medium uppercase tracking-wide text-zinc-600">Tools</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {a.tools.map((t) => (
                    <Mono key={t}>{t}</Mono>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-3 text-[10px] text-zinc-600">v{a.version}</div>
          </Card>
        ))}
      </div>
    </div>
  );
}
