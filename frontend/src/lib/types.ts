// Mirrors src/bulwark/platform/models.py + api/routes.py response shapes
// exactly -- field names are copy-checked against the Python dataclasses,
// not guessed.

export type VendorTier = "critical" | "high" | "moderate" | "low";
export type VendorStatus =
  | "onboarding"
  | "active"
  | "under_review"
  | "offboarding"
  | "offboarded";

export interface Vendor {
  vendor_id: string;
  tenant: string;
  name: string;
  tier: VendorTier;
  data_classes: string[];
  status: VendorStatus;
  last_assessed_at: string | null;
  next_review_due: string | null;
  blind_window_days: number | null;
}

export type FindingStatus = "satisfied" | "gap" | "exception" | "unknown";

export interface HumanDecision {
  actor: string;
  decision: string;
  rationale: string;
  decided_at?: string;
}

export interface Finding {
  finding_id: string;
  tenant: string;
  vendor_id: string;
  control_ref: string;
  status: FindingStatus;
  gap_description: string;
  residual_risk: number;
  evidence_ids: string[];
  assertion_ids: string[];
  trace_id: string;
  requires_human: boolean;
  human_decision: HumanDecision | null;
}

export interface ReasoningConsidered {
  option: string;
  score: number;
  why_not?: string;
  chosen?: boolean;
}

export interface ReasoningRecord {
  decision_id: string;
  subject_id: string;
  trace_id: string;
  agent: string;
  inputs_hash: string;
  considered: ReasoningConsidered[];
  evidence_ids: string[];
  assertion_ids: string[];
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  created_at?: string;
}

export interface ExplainResponse {
  finding: Finding;
  reasoning: ReasoningRecord[];
}

export type ClauseRisk = "critical" | "high" | "medium" | "low";

export interface ContractTerm {
  term_id: string;
  tenant: string;
  vendor_id: string;
  artifact_id: string;
  clause_type: string;
  clause_text: string;
  risk_level: ClauseRisk;
  playbook_requirement: string;
  deviation: string;
  source_page: number | null;
  created_at: string;
}

export interface Subprocessor {
  subprocessor_id: string;
  tenant: string;
  vendor_id: string;
  artifact_id: string;
  name: string;
  purpose: string;
  location: string;
  created_at: string;
}

export interface ConcentrationRisk {
  risk_id: string;
  tenant: string;
  subprocessor_name: string;
  vendor_ids: string[];
  critical_vendor_count: number;
  severity: ClauseRisk;
  detail: string;
  detected_at: string;
}

export interface AssessmentSnapshot {
  snapshot_id: string;
  tenant: string;
  vendor_id: string;
  control_ref: string;
  status: string;
  residual_risk: number;
  finding_id: string;
  trace_id: string;
  created_at: string;
}

export interface CrosswalkCoveredControl {
  target_control: string;
  via_soc2_control: string;
  source_finding_id: string;
}

export interface CrosswalkGapControl {
  target_control: string;
  via_soc2_control: string;
  reason: string;
}

export interface CrosswalkResponse {
  vendor_id: string;
  target_framework: string;
  covered_controls: CrosswalkCoveredControl[];
  gap_controls: CrosswalkGapControl[];
  coverage_pct: number;
}

export type OffboardingStatus = "pending" | "confirmed";

export interface OffboardingRecord {
  record_id: string;
  tenant: string;
  vendor_id: string;
  reason: string;
  initiated_at: string;
  deadline: string;
  status: OffboardingStatus;
  confirmed_at: string | null;
  evidence_note: string | null;
}

export interface Questionnaire {
  questionnaire_id: string;
  tenant: string;
  buyer: string;
  received_at: string;
  deadline: string | null;
  total_questions: number;
  auto_answered: number;
  abstained: number;
  status: "processing" | "ready_for_review" | "completed";
}

export type AnswerStatus = "auto" | "needs_human" | "approved" | "blocked_dlp";

export interface Answer {
  answer_id: string;
  questionnaire_id: string;
  question: string;
  answer: string;
  confidence: number;
  citations: string[];
  status: AnswerStatus;
}

export interface QuestionnaireDetail extends Questionnaire {
  answers: Answer[];
}

export interface AgentRecord {
  agent_id: string;
  name: string;
  version: string;
  description: string;
  model: string;
  trust_zone: string;
  autonomy_ceiling: number;
  departments: string[];
  tools: string[];
}

export interface FleetHealthAgent {
  agent_id: string;
  trust_zone: string;
  autonomy_ceiling: number;
  paused: boolean;
  effective_ceiling: number;
}

export interface DailySpend {
  date?: string;
  tokens_in?: number;
  tokens_out?: number;
  usd?: number;
  [key: string]: unknown;
}

export interface FleetHealth {
  global_autonomy_level: number;
  agents: FleetHealthAgent[];
  dlq_depth: number;
  spend_today: DailySpend;
  spend_cap_usd: number;
}

export interface FleetConfig {
  autonomy_level: number;
  max_daily_token_spend: number;
  paused_agents: string[];
}

export interface Metrics {
  blind_window_avg_days: number | null;
  vendor_count: number;
  questions_auto_answered_pct: number;
  findings_traceable_to_evidence_pct: number;
  control_coverage_fresh_evidence_pct: number;
  injection_attempts_blocked: number;
  findings_requiring_human_review: number;
  note: string;
}

export interface Digest {
  digest_id: string;
  tenant: string;
  trace_id: string;
  narrative: string;
  highlights: string[];
  inputs: Record<string, unknown>;
  generated_at: string;
}

export interface AuditEntry {
  entry_id: string;
  ts: string;
  agent_name: string;
  event: string;
  detail: string;
  invocation_id: string | null;
  trace_id: string | null;
  vendor_id?: string | null;
}

export interface TraceResponse {
  trace_id: string;
  entries: AuditEntry[];
}

export interface TraceSummary {
  trace_id: string;
  vendor_id: string | null;
  started_at: string;
  last_event_at: string;
  event_count: number;
  last_event: string;
  status: "completed" | "running";
}

export interface DlqEntry {
  topic?: string;
  event_id?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface SubmitArtifactResponse {
  trace_id: string;
  status: string;
  vendor_id: string;
  artifact_id: string;
  armor_verdict: string;
  summary?: string;
}

export interface SubmitQuestionnaireResponse {
  trace_id: string;
  questionnaire_id: string;
  summary: string;
}
