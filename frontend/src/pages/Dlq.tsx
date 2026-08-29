import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "../lib/api";
import { Card, Table, Th, Td, Tr, Badge, LoadingBlock, ErrorBlock, EmptyBlock, Mono } from "../components/ui";
import { ChevronDown, ChevronUp } from "lucide-react";

// A DLQ `reason` is often a full Python traceback -- hundreds of lines,
// file paths and all. Showing that inline (as this page used to) made a
// 4-entry queue render as a ~7000px wall of text with the actual failure
// (usually one short line, e.g. a 429 RESOURCE_EXHAUSTED) buried inside
// it. Collapse to that first line by default; expand on demand into a
// scrollable, monospace block instead of blowing out the page.
function firstLine(reason: string): string {
  const line = reason.split("\n")[0].trim();
  return line.length > 140 ? line.slice(0, 140) + "…" : line;
}

function ReasonCell({ reason }: { reason: string }) {
  const [expanded, setExpanded] = useState(false);
  const isMultiline = reason.includes("\n") || reason.length > 140;

  if (!isMultiline) {
    return <span className="text-zinc-400">{reason}</span>;
  }

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1 text-left text-zinc-400 hover:text-zinc-200"
      >
        {expanded ? <ChevronUp className="h-3 w-3 shrink-0" /> : <ChevronDown className="h-3 w-3 shrink-0" />}
        <span>{firstLine(reason)}</span>
      </button>
      {expanded && (
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 font-mono text-xs text-zinc-400">
          {reason}
        </pre>
      )}
    </div>
  );
}

export default function Dlq() {
  const api = useApi();
  const dlq = useQuery({ queryKey: ["dlq"], queryFn: () => api.getDlq(), refetchInterval: 15000 });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Dead-Letter Queue</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Events that failed to process on the event bus — inspect and re-drive manually.
        </p>
      </div>

      {dlq.isLoading && <LoadingBlock label="Loading DLQ…" />}
      {dlq.isError && <ErrorBlock message={(dlq.error as Error).message} />}

      {dlq.data && (
        <Card title={`${dlq.data.length} entr${dlq.data.length === 1 ? "y" : "ies"}`}>
          {dlq.data.length === 0 ? (
            <EmptyBlock label="Empty — nothing has failed to process." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Topic</Th>
                  <Th>Event ID</Th>
                  <Th>Reason</Th>
                </tr>
              </thead>
              <tbody>
                {dlq.data.map((d, i) => {
                  const reason = String(d.reason ?? JSON.stringify(d));
                  return (
                    <Tr key={i}>
                      <Td>
                        <Badge tone="red">{String(d.topic ?? "unknown")}</Badge>
                      </Td>
                      <Td>
                        <Mono>{String(d.event_id ?? "—")}</Mono>
                      </Td>
                      <Td className="max-w-lg">
                        <ReasonCell reason={reason} />
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Card>
      )}
    </div>
  );
}
