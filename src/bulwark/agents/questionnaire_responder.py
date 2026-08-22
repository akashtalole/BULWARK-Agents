"""Questionnaire Responder (`questionnaire-responder`): answers a buyer's
security questionnaire from the evidence graph, with a citation on every
answer and an honest confidence score -- and abstains rather than guesses.

Two independent gates run on every drafted answer, in code:

1. **Confidence threshold** (`ANSWER_CONFIDENCE_THRESHOLD`, default 0.75)
   -- below it, the answer is marked `needs_human` regardless of how
   confident the model's own text sounds.
2. **Egress DLP scan** (`guardrails.scan_for_dlp_violation`, standing in
   for a real Cloud DLP inspection job) -- an answer that would leak an
   internal hostname, a credential-shaped string, or raw PII is marked
   `blocked_dlp` and routed to a human even if confidence was high.

A system that answers most of a questionnaire with citations and flags
the rest honestly is the actual product here; a system that answers 100%
with unverifiable confidence is a liability, not a feature.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.config import settings
from bulwark.platform import guardrails, identity, policy
from bulwark.platform.models import Answer, answer_repo, control_repo, evidence_repo, questionnaire_repo
from bulwark.platform.observability import audit_log


def search_evidence(query: str) -> list[dict]:
    """Search the control-evidence graph for material relevant to a
    questionnaire question. Stands in for a Vertex AI Vector Search
    retrieval over the same graph in production; here it's a substring
    match over control titles/requirement text, which is enough to
    demonstrate citation-grounded answering without a live vector index.

    Args:
        query: Free-text question or keywords, e.g. "multi-factor authentication".

    Returns:
        Matching controls with their latest evidence, each item citable
        by its `control_ref` or `evidence_id`.
    """
    query_lower = query.lower()
    results = []
    for control in control_repo.list(settings.default_tenant):
        haystack = f"{control.title} {control.requirement_text}".lower()
        if not any(word in haystack for word in query_lower.split() if len(word) > 3):
            continue
        latest = evidence_repo.latest_for_control(settings.default_tenant, control.control_ref)
        results.append(
            {
                "control_ref": control.control_ref,
                "title": control.title,
                "evidence_id": latest.evidence_id if latest else None,
                "observed_value": latest.observed_value if latest else None,
                "satisfied": latest.satisfied if latest else None,
                "freshness": latest.freshness if latest else None,
            }
        )
    return results


def draft_answer(questionnaire_id: str, question: str, answer: str, confidence: float, citations: list[str]) -> dict:
    """Draft one answer to a questionnaire question. Confidence below the
    configured threshold, or a failed egress scan, routes the answer to a
    human instead of marking it ready.

    Args:
        questionnaire_id: The questionnaire this answer belongs to.
        question: The buyer's question, verbatim.
        answer: Your drafted answer.
        confidence: Your honest confidence (0.0-1.0) that this answer is correct and complete.
        citations: control_ref or evidence_id values from `search_evidence` backing this answer.

    Returns:
        The answer_id and the status it was assigned.
    """
    identity.require_grant("questionnaire-responder", "answers:write")
    policy.enforce_autonomy("questionnaire-responder", 1)  # L1 Draft: nothing leaves the system yet

    if confidence < settings.answer_confidence_threshold or not citations:
        status = "needs_human"
    else:
        blocked, kinds = guardrails.scan_for_dlp_violation(answer)
        if blocked:
            status = "blocked_dlp"
            audit_log.record(
                agent_name="questionnaire-responder",
                event="answer_blocked_dlp",
                detail=f"questionnaire={questionnaire_id} question={question!r} dlp_kinds={kinds}",
            )
        else:
            status = "auto"

    record = answer_repo.create(
        Answer(
            answer_id=f"ans_{questionnaire_id[-6:]}_{len(answer_repo.list_for_questionnaire(questionnaire_id))}",
            questionnaire_id=questionnaire_id,
            question=question,
            answer=answer,
            confidence=confidence,
            citations=citations,
            status=status,  # type: ignore[arg-type]
        )
    )

    all_answers = answer_repo.list_for_questionnaire(questionnaire_id)
    auto = sum(1 for a in all_answers if a.status == "auto")
    abstained = sum(1 for a in all_answers if a.status in ("needs_human", "blocked_dlp"))
    questionnaire_repo.update(
        questionnaire_id,
        total_questions=len(all_answers),
        auto_answered=auto,
        abstained=abstained,
        status="ready_for_review",
    )
    return {"answer_id": record.answer_id, "status": status}


questionnaire_responder_agent = LlmAgent(
    name="questionnaire_responder_agent",
    model=settings.gemini_flash_model,
    description="Answers buyer questionnaires from the evidence graph, with citations, confidence, and abstention.",
    instruction=(
        f"You are the Questionnaire Responder for a third-party risk fleet. Given a "
        f"questionnaire_id and a list of questions, for each question: call "
        f"`search_evidence` with the key terms to find relevant controls, then draft an "
        f"answer grounded only in what `search_evidence` returned. Set confidence "
        f"honestly -- if the evidence is thin, contradicts the likely answer, or you're "
        f"not sure, use a LOW confidence rather than writing a confident-sounding "
        f"guess; anything below {settings.answer_confidence_threshold} will correctly "
        f"be routed to a human, which is the intended outcome, not a failure. Call "
        f"`draft_answer` once per question with your answer, confidence, and the "
        f"control_ref/evidence_id citations backing it. Never answer a question with no "
        f"citations at all -- if `search_evidence` found nothing relevant, still call "
        f"`draft_answer` with low confidence and an empty citations list so it's routed "
        f"to a human."
    ),
    tools=[FunctionTool(search_evidence), FunctionTool(draft_answer)],
)
