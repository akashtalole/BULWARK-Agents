import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { Card, Button, Badge, LoadingBlock, ErrorBlock, Mono } from "../components/ui";
import { formatDate } from "../lib/format";
import { Sparkles, ChevronDown, ChevronRight } from "lucide-react";

export default function Digest() {
  const api = useApi();
  const qc = useQueryClient();
  const [showInputs, setShowInputs] = useState(false);

  const latest = useQuery({
    queryKey: ["digest-latest"],
    queryFn: () => api.getLatestDigest(),
    retry: false,
  });

  const generate = useMutation({
    mutationFn: () => api.generateDigest(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["digest-latest"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Executive Risk Digest</h1>
          <p className="mt-1 text-sm text-zinc-500">
            The fleet's 44 endpoints of state, turned into a short narrative — grounded only in
            what's shown below.
          </p>
        </div>
        <Button variant="primary" disabled={generate.isPending} onClick={() => generate.mutate()}>
          <Sparkles className="h-3.5 w-3.5" />
          {generate.isPending ? "Generating…" : "Generate now"}
        </Button>
      </div>
      {generate.isError && <ErrorBlock message={(generate.error as ApiError).message} />}

      {latest.isLoading && <LoadingBlock label="Loading latest digest…" />}
      {latest.isError && (
        <Card>
          <div className="text-sm text-zinc-500">
            No digest has been generated yet — click "Generate now" (requires Gemini credentials).
          </div>
        </Card>
      )}

      {latest.data && (
        <>
          <Card
            title="Latest digest"
            subtitle={`generated ${formatDate(latest.data.generated_at)} · trace ${latest.data.trace_id}`}
          >
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
              {latest.data.narrative}
            </p>
          </Card>

          <Card title="Highlights">
            {latest.data.highlights.length === 0 ? (
              <div className="text-sm text-zinc-500">None.</div>
            ) : (
              <ul className="space-y-2">
                {latest.data.highlights.map((h, i) => (
                  <li key={i} className="flex gap-2 text-sm text-zinc-300">
                    <Badge tone="blue" className="mt-0.5 shrink-0">
                      {i + 1}
                    </Badge>
                    {h}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <button
              onClick={() => setShowInputs((s) => !s)}
              className="flex w-full items-center gap-1.5 text-sm font-medium text-zinc-300"
            >
              {showInputs ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Grounding inputs
              <span className="font-normal text-zinc-600">
                — the exact snapshot the narrative was written from
              </span>
            </button>
            {showInputs && (
              <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-zinc-950 p-3 text-xs text-zinc-400">
                {JSON.stringify(latest.data.inputs, null, 2)}
              </pre>
            )}
          </Card>

          <div className="text-xs text-zinc-600">
            Look up a past digest by id: <Mono>GET /digest/&#123;id&#125;</Mono>
          </div>
        </>
      )}
    </div>
  );
}
