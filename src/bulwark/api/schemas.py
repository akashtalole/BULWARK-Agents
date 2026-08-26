from __future__ import annotations

from pydantic import BaseModel, Field


class SubmitArtifactRequest(BaseModel):
    vendor_name: str = Field(..., min_length=1, max_length=200)
    doc_type: str = Field(..., min_length=1, max_length=50)
    raw_text: str = Field(..., min_length=1, max_length=20000)
    gcs_uri: str = Field(default="gs://bulwark-quarantine/demo-upload")
    sha256: str = Field(default="demo-sha")


class SubmitArtifactResponse(BaseModel):
    trace_id: str
    status: str
    vendor_id: str | None = None
    artifact_id: str | None = None
    armor_verdict: str | None = None
    summary: str | None = None


class SubmitQuestionnaireRequest(BaseModel):
    buyer: str = Field(..., min_length=1, max_length=200)
    questions: list[str] = Field(..., min_length=1, max_length=100)


class SubmitQuestionnaireResponse(BaseModel):
    trace_id: str
    questionnaire_id: str
    summary: str


class HumanDecisionRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=100)
    decision: str = Field(..., min_length=1, max_length=100)
    rationale: str = Field(..., min_length=1, max_length=2000)


class AutonomyRequest(BaseModel):
    autonomy_level: int | None = None
    pause_agent_id: str | None = None
    resume_agent_id: str | None = None


class RegisterVendorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    tier: str = Field(default="moderate")
    data_classes: list[str] = Field(default_factory=list)


class TriggerAssessmentRequest(BaseModel):
    vendor_id: str = Field(..., min_length=1)
    scope: str = Field(default="full")
    reason: str = Field(default="manually_triggered")


class GenericDecisionRequest(BaseModel):
    subject_id: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1, max_length=100)
    decision: str = Field(..., min_length=1, max_length=100)
    rationale: str = Field(..., min_length=1, max_length=2000)


class OffboardVendorRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ConfirmDataDeletionRequest(BaseModel):
    evidence_note: str = Field(..., min_length=1, max_length=2000)


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


class UpdateQuestionnaireRequest(BaseModel):
    buyer: str | None = Field(default=None, min_length=1, max_length=200)
    # A full replacement of the question set, not a delta -- matches
    # questions to existing answers by exact text so unchanged questions
    # keep their answer; anything new is added unanswered (needs_human),
    # anything dropped has its answer removed. See update_questionnaire.
    questions: list[str] | None = Field(default=None, min_length=1, max_length=100)
