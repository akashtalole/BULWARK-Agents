import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useRecentIds } from "../lib/recent";
import { Card, Button, Input, Textarea, ErrorBlock, EmptyBlock, Mono } from "../components/ui";
import { Send, Search } from "lucide-react";

export default function Questionnaires() {
  const api = useApi();
  const navigate = useNavigate();
  const { ids, add } = useRecentIds("questionnaires");

  const [buyer, setBuyer] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [lookupId, setLookupId] = useState("");

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
      add(res.questionnaire_id);
      navigate(`/questionnaires/${res.questionnaire_id}`);
    },
  });

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
        title="Look up a questionnaire"
        subtitle="the API has no list endpoint by design (api/routes.py) — paste an id or pick a recent one below"
      >
        <div className="flex items-end gap-2">
          <Input value={lookupId} onChange={setLookupId} placeholder="quest_xxxxxx" className="w-64" />
          <Button
            disabled={!lookupId}
            onClick={() => navigate(`/questionnaires/${lookupId}`)}
          >
            <Search className="h-3.5 w-3.5" /> Open
          </Button>
        </div>
      </Card>

      <Card title="Recently submitted (this browser)">
        {ids.length === 0 ? (
          <EmptyBlock label="Nothing submitted from this browser yet." />
        ) : (
          <div className="space-y-1">
            {ids.map((id) => (
              <button
                key={id}
                onClick={() => navigate(`/questionnaires/${id}`)}
                className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm hover:bg-zinc-800/60"
              >
                <Mono>{id}</Mono>
              </button>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
