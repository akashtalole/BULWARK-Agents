import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useSort } from "../lib/sort";
import { formatDate } from "../lib/format";
import type { Questionnaire } from "../lib/types";
import {
  Card,
  Table,
  Th,
  Td,
  Tr,
  Badge,
  Button,
  Input,
  Textarea,
  ErrorBlock,
  EmptyBlock,
  LoadingBlock,
  Mono,
} from "../components/ui";
import { Send } from "lucide-react";

export default function Questionnaires() {
  const api = useApi();
  const navigate = useNavigate();

  const [buyer, setBuyer] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [search, setSearch] = useState("");
  const sort = useSort<Questionnaire>();

  const questionnaires = useQuery({ queryKey: ["questionnaires"], queryFn: () => api.listQuestionnaires() });

  const submit = useMutation({
    mutationFn: () =>
      api.submitQuestionnaire(
        buyer,
        questionsRaw
          .split("\n")
          .map((q) => q.trim())
          .filter(Boolean),
      ),
    onSuccess: (res) => {
      navigate(`/questionnaires/${res.questionnaire_id}`);
    },
  });

  const rows = questionnaires.data
    ? sort.apply(questionnaires.data.filter((q) => q.buyer.toLowerCase().includes(search.toLowerCase())))
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Questionnaires</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Answered from the same evidence graph that assesses your vendors — citations on every
          confident answer, honest abstention on the rest.
        </p>
      </div>

      <Card
        title="Submit a questionnaire"
        subtitle="POST /questionnaires — requires Gemini credentials to run the Attest loop"
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Buyer</label>
            <Input value={buyer} onChange={setBuyer} placeholder="BigBuyer Corp" className="w-full max-w-sm" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Questions (one per line)</label>
            <Textarea
              value={questionsRaw}
              onChange={setQuestionsRaw}
              rows={5}
              placeholder={"Do you enforce MFA for all employee access?\nDo you use post-quantum cryptography everywhere?"}
            />
          </div>
          <Button
            variant="primary"
            disabled={!buyer || !questionsRaw.trim() || submit.isPending}
            onClick={() => submit.mutate()}
          >
            <Send className="h-3.5 w-3.5" />
            {submit.isPending ? "Submitting…" : "Submit"}
          </Button>
          {submit.isError && <ErrorBlock message={(submit.error as ApiError).message} />}
        </div>
      </Card>

      <Card
        title="All questionnaires"
        subtitle="GET /questionnaires"
        actions={
          <Input value={search} onChange={setSearch} placeholder="Search by buyer…" className="w-56" />
        }
      >
        {questionnaires.isLoading ? (
          <LoadingBlock label="Loading questionnaires…" />
        ) : questionnaires.isError ? (
          <ErrorBlock message={(questionnaires.error as Error).message} />
        ) : rows.length === 0 ? (
          <EmptyBlock label={search ? "No questionnaires match." : "Nothing submitted yet."} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th onClick={() => sort.toggle("buyer")} sortDirection={sort.directionFor("buyer")}>
                  Buyer
                </Th>
                <Th onClick={() => sort.toggle("received_at")} sortDirection={sort.directionFor("received_at")}>
                  Received
                </Th>
                <Th
                  onClick={() => sort.toggle("total_questions")}
                  sortDirection={sort.directionFor("total_questions")}
                >
                  Questions
                </Th>
                <Th onClick={() => sort.toggle("auto_answered")} sortDirection={sort.directionFor("auto_answered")}>
                  Auto-answered
                </Th>
                <Th onClick={() => sort.toggle("status")} sortDirection={sort.directionFor("status")}>
                  Status
                </Th>
                <Th>Id</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((q) => (
                <Tr key={q.questionnaire_id} onClick={() => navigate(`/questionnaires/${q.questionnaire_id}`)}>
                  <Td className="font-medium text-zinc-100">{q.buyer}</Td>
                  <Td className="text-zinc-500">{formatDate(q.received_at)}</Td>
                  <Td>{q.total_questions}</Td>
                  <Td>{q.auto_answered}</Td>
                  <Td>
                    <Badge>{q.status}</Badge>
                  </Td>
                  <Td>
                    <Mono>{q.questionnaire_id}</Mono>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
