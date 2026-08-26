import { useMemo } from "react";
import { useSettings } from "./settings";
import type {
  AgentRecord,
  AssessmentSnapshot,
  ConcentrationRisk,
  ContractTerm,
  CrosswalkResponse,
  Digest,
  DlqEntry,
  ExplainResponse,
  FleetConfig,
  FleetHealth,
  Finding,
  Metrics,
  OffboardingRecord,
  Questionnaire,
  QuestionnaireDetail,
  Subprocessor,
  SubmitArtifactResponse,
  SubmitQuestionnaireResponse,
  TraceResponse,
  Vendor,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** Thin typed fetch wrapper over BULWARK's Agent Gateway (api/routes.py).
 * Every call sends X-API-Key; a non-2xx response raises ApiError with the
 * server's own `detail` message, which every route already returns via
 * FastAPI's HTTPException. */
export class BulwarkClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "X-API-Key": this.apiKey,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        // body wasn't JSON -- fall back to statusText
      }
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  private get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  private post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
  }

  private patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined });
  }

  healthz(): Promise<{ status: string }> {
    return this.get("/healthz");
  }

  // ----------------------------------------------------------------- auth
  getAuthConfig(): Promise<{ login_required: boolean }> {
    return this.get("/auth/config");
  }

  login(password: string): Promise<{ api_key: string }> {
    return this.post("/auth/login", { password });
  }

  // ------------------------------------------------------------- registry
  listRegistry(): Promise<AgentRecord[]> {
    return this.get("/registry");
  }

  // -------------------------------------------------------------- vendors
  registerVendor(payload: { name: string; tier: string; data_classes?: string[] }): Promise<Vendor> {
    return this.post("/vendors", payload);
  }

  submitArtifact(payload: {
    vendor_name: string;
    doc_type: string;
    raw_text: string;
    gcs_uri?: string;
    sha256?: string;
  }): Promise<SubmitArtifactResponse> {
    return this.post("/vendors/artifacts", payload);
  }

  listVendors(): Promise<Vendor[]> {
    return this.get("/vendors");
  }

  getVendor(vendorId: string): Promise<Vendor> {
    return this.get(`/vendors/${vendorId}`);
  }

  getVendorFindings(vendorId: string): Promise<Finding[]> {
    return this.get(`/vendors/${vendorId}/findings`);
  }

  getVendorContractTerms(vendorId: string): Promise<ContractTerm[]> {
    return this.get(`/vendors/${vendorId}/contract-terms`);
  }

  getVendorSubprocessors(vendorId: string): Promise<Subprocessor[]> {
    return this.get(`/vendors/${vendorId}/subprocessors`);
  }

  getVendorAssessmentHistory(vendorId: string): Promise<AssessmentSnapshot[]> {
    return this.get(`/vendors/${vendorId}/assessment-history`);
  }

  getVendorCrosswalk(vendorId: string, targetFramework = "ISO27001"): Promise<CrosswalkResponse> {
    return this.get(`/vendors/${vendorId}/crosswalk?target_framework=${encodeURIComponent(targetFramework)}`);
  }

  offboardVendor(vendorId: string, reason: string): Promise<{ record_id: string; vendor_id: string; deadline: string }> {
    return this.post(`/vendors/${vendorId}/offboard`, { reason });
  }

  confirmDataDeletion(vendorId: string, evidenceNote: string): Promise<{ record_id: string; vendor_id: string; status: string }> {
    return this.post(`/vendors/${vendorId}/offboard/confirm`, { evidence_note: evidenceNote });
  }

  getVendorOffboarding(vendorId: string): Promise<OffboardingRecord> {
    return this.get(`/vendors/${vendorId}/offboarding`);
  }

  // ---------------------------------------------------------- assessments
  triggerAssessment(vendorId: string, reason: string, scope?: string): Promise<{ trace_id: string; vendor_id: string; status: string }> {
    return this.post("/assessments", { vendor_id: vendorId, reason, scope });
  }

  getAssessmentStatus(traceId: string): Promise<{ trace_id: string; status: string; findings: Finding[]; run_checkpoint: unknown }> {
    return this.get(`/assessments/${traceId}`);
  }

  // -------------------------------------------------------------- findings
  listFindings(status?: string): Promise<Finding[]> {
    return this.get(`/findings${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  }

  getFinding(findingId: string): Promise<Finding> {
    return this.get(`/findings/${findingId}`);
  }

  explainFinding(findingId: string): Promise<ExplainResponse> {
    return this.get(`/findings/${findingId}/explain`);
  }

  recordFindingDecision(findingId: string, actor: string, decision: string, rationale: string): Promise<Finding> {
    return this.post(`/findings/${findingId}/decision`, { actor, decision, rationale });
  }

  // --------------------------------------------------------- questionnaires
  submitQuestionnaire(buyer: string, questions: string[]): Promise<SubmitQuestionnaireResponse> {
    return this.post("/questionnaires", { buyer, questions });
  }

  listQuestionnaires(): Promise<Questionnaire[]> {
    return this.get("/questionnaires");
  }

  getQuestionnaire(questionnaireId: string): Promise<QuestionnaireDetail> {
    return this.get(`/questionnaires/${questionnaireId}`);
  }

  updateQuestionnaire(
    questionnaireId: string,
    patch: { buyer?: string; questions?: string[] },
  ): Promise<QuestionnaireDetail> {
    return this.patch(`/questionnaires/${questionnaireId}`, patch);
  }

  exportQuestionnaire(questionnaireId: string): Promise<{
    questionnaire_id: string;
    exported: unknown[];
    excluded_count: number;
    excluded_reasons: Record<string, string>;
  }> {
    return this.post(`/questionnaires/${questionnaireId}/export`);
  }

  // -------------------------------------------------------------------runs
  rollbackRun(traceId: string): Promise<{ trace_id: string; reverted: unknown[] }> {
    return this.post(`/runs/${traceId}/rollback`);
  }

  // ---------------------------------------------------------------- sweeps
  tickEvidenceCollector(): Promise<{ collected: number; run_id: string; records: unknown[] }> {
    return this.post("/evidence-collector/tick");
  }

  tickDriftSentinel(): Promise<{ trace_id: string; summary: string }> {
    return this.post("/drift-sentinel/tick");
  }

  tickConcentrationAnalyzer(): Promise<{ clusters_detected: number; risks: ConcentrationRisk[] }> {
    return this.post("/concentration-analyzer/tick");
  }

  listConcentrationRisks(): Promise<ConcentrationRisk[]> {
    return this.get("/concentration-risks");
  }

  // --------------------------------------------------------- observability
  getTrace(traceId: string): Promise<TraceResponse> {
    return this.get(`/traces/${traceId}`);
  }

  getDlq(): Promise<DlqEntry[]> {
    return this.get("/dlq");
  }

  // ------------------------------------------------------------ fleet mgmt
  getFleetConfig(): Promise<FleetConfig> {
    return this.get("/fleet-config");
  }

  updateFleetConfig(payload: {
    autonomy_level?: number;
    pause_agent_id?: string;
    resume_agent_id?: string;
  }): Promise<FleetConfig> {
    return this.post("/fleet-config", payload);
  }

  getFleetHealth(): Promise<FleetHealth> {
    return this.get("/fleet/health");
  }

  getMetrics(): Promise<Metrics> {
    return this.get("/metrics");
  }

  // ------------------------------------------------------------------digest
  generateDigest(): Promise<{ trace_id: string; digest_id: string | null }> {
    return this.post("/digest/generate");
  }

  getLatestDigest(): Promise<Digest> {
    return this.get("/digest/latest");
  }

  getDigest(digestId: string): Promise<Digest> {
    return this.get(`/digest/${digestId}`);
  }
}

export function useApi(): BulwarkClient {
  const { baseUrl, apiKey } = useSettings();
  return useMemo(() => new BulwarkClient(baseUrl, apiKey), [baseUrl, apiKey]);
}
