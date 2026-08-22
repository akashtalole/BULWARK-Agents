import { useQuery } from "@tanstack/react-query";
import { useApi } from "../lib/api";
import { Card, Table, Th, Td, Tr, Badge, LoadingBlock, ErrorBlock, EmptyBlock, Mono } from "../components/ui";

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
                {dlq.data.map((d, i) => (
                  <Tr key={i}>
                    <Td>
                      <Badge tone="red">{String(d.topic ?? "unknown")}</Badge>
                    </Td>
                    <Td>
                      <Mono>{String(d.event_id ?? "—")}</Mono>
                    </Td>
                    <Td className="max-w-md text-zinc-400">{String(d.reason ?? JSON.stringify(d))}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}
    </div>
  );
}
