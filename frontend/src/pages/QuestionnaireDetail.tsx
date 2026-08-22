import { useParams, Link } from "react-router-dom";
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
  LoadingBlock,
  ErrorBlock,
  Mono,
  toneForAnswerStatus,
} from "../components/ui";
import { ArrowLeft, Download } from "lucide-react";

export default function QuestionnaireDetail() {
  const { questionnaireId } = useParams<{ questionnaireId: string }>();
  const api = useApi();
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["questionnaire", questionnaireId],
    queryFn: () => api.getQuestionnaire(questionnaireId!),
    enabled: !!questionnaireId,
  });

  const exportMutation = useMutation({
    mutationFn: () => api.exportQuestionnaire(questionnaireId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["questionnaire", questionnaireId] }),
  });

  if (q.isLoading) return <LoadingBlock label="Loading questionnaire…" />;
  if (q.isError) return <ErrorBlock message={(q.error as Error).message} />;
  const data = q.data!;

  return (
    <div className="space-y-6">
      <Link to="/questionnaires" className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300">
        <ArrowLeft className="h-3 w-3" /> Back to questionnaires
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">{data.buyer}</h1>
          <Mono className="mt-1">{data.questionnaire_id}</Mono>
        </div>
        <Button variant="primary" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
          <Download className="h-3.5 w-3.5" />
          {exportMutation.isPending ? "Exporting…" : "Export (auto-status only)"}
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <div className="text-xs text-zinc-500">Status</div>
          <Badge>{data.status}</Badge>
        </Card>
        <Card>
          <div className="text-xs text-zinc-500">Total questions</div>
          <div className="text-lg font-semibold text-zinc-100">{data.total_questions}</div>
        </Card>
        <Card>
          <div className="text-xs text-zinc-500">Auto-answered</div>
          <div className="text-lg font-semibold text-emerald-400">{data.auto_answered}</div>
        </Card>
        <Card>
          <div className="text-xs text-zinc-500">Abstained</div>
          <div className="text-lg font-semibold text-amber-400">{data.abstained}</div>
        </Card>
      </div>

      {exportMutation.isSuccess && (
        <Card title="Export result">
          <div className="text-sm text-zinc-300">
            {exportMutation.data.exported.length} answer(s) exported · {exportMutation.data.excluded_count} excluded
          </div>
          {Object.keys(exportMutation.data.excluded_reasons).length > 0 && (
            <div className="mt-2 text-xs text-zinc-500">
              {Object.entries(exportMutation.data.excluded_reasons).map(([id, reason]) => (
                <div key={id}>
                  <Mono>{id}</Mono> — {reason}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
      {exportMutation.isError && <ErrorBlock message={(exportMutation.error as ApiError).message} />}

      <Card title="Answers">
        <Table>
          <thead>
            <tr>
              <Th>Question</Th>
              <Th>Answer</Th>
              <Th>Confidence</Th>
              <Th>Status</Th>
              <Th>Citations</Th>
            </tr>
          </thead>
          <tbody>
            {data.answers.map((a) => (
              <Tr key={a.answer_id}>
                <Td className="max-w-xs font-medium text-zinc-100">{a.question}</Td>
                <Td className="max-w-sm text-zinc-300">{a.answer}</Td>
                <Td className="tabular-nums">{a.confidence.toFixed(2)}</Td>
                <Td>
                  <Badge tone={toneForAnswerStatus(a.status)}>{a.status}</Badge>
                </Td>
                <Td>
                  {a.citations.length === 0 ? (
                    <span className="text-zinc-600">none</span>
                  ) : (
                    a.citations.map((c) => <Mono key={c}>{c}</Mono>)
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
