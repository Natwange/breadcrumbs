import { getSupabaseClient, isSupabaseConfigured } from "@/lib/supabase";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Backend responded with ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(options.headers);

  if (isSupabaseConfigured) {
    const supabase = getSupabaseClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (session?.access_token) {
      headers.set("Authorization", `Bearer ${session.access_token}`);
    }
  }

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string | null;
  organization: {
    id: string;
    name: string;
    slug: string;
    onboarding_status: string;
  };
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const response = await apiFetch("/auth/me");
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return (await response.json()) as CurrentUser;
}

async function toError(response: Response): Promise<Error> {
  let detail = `Request failed with ${response.status}`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body?.detail) detail = body.detail;
  } catch {
    // Non-JSON error body.
  }
  return new Error(detail);
}

// --- Incidents ----------------------------------------------------------------

export interface Incident {
  id: string;
  title: string;
  description: string | null;
  status: string;
  severity: string | null;
  created_at: string;
}

export async function listIncidents(): Promise<Incident[]> {
  const response = await apiFetch("/incidents");
  if (!response.ok) throw await toError(response);
  return (await response.json()) as Incident[];
}

export async function getIncident(incidentId: string): Promise<Incident> {
  const response = await apiFetch(`/incidents/${incidentId}`);
  if (!response.ok) throw await toError(response);
  return (await response.json()) as Incident;
}

export async function createIncident(payload: {
  title: string;
  description?: string;
  severity?: string;
}): Promise<Incident> {
  const response = await apiFetch("/incidents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as Incident;
}

export async function resolveIncident(incidentId: string): Promise<Incident> {
  const response = await apiFetch(`/incidents/${incidentId}/resolve`, {
    method: "POST",
  });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as Incident;
}

// --- Investigation runs -------------------------------------------------------

export interface InvestigationRun {
  id: string;
  incident_id: string | null;
  status: string;
  trigger: string | null;
  summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  evidence_count: number;
  timeline_count: number;
}

export interface InvestigationRunDetail extends InvestigationRun {
  executive_summary: string | null;
  reasoning_status: string | null;
  hypothesis: {
    id: string;
    title: string;
    description: string | null;
    status: string;
    confidence: number | null;
  } | null;
  slack_draft: {
    id: string;
    channel: string | null;
    content: string | null;
    status: string;
  } | null;
}

export interface EvidenceItem {
  id: string;
  source: string;
  evidence_type: string;
  title: string | null;
  content: string | null;
  relevance_score: number | null;
  relevance_label: string | null;
  relevance_confidence: string | null;
  relevance_reason: string | null;
  observed_at: string | null;
}

export interface TimelineItem {
  id: string;
  event_time: string | null;
  title: string;
  description: string | null;
  source: string | null;
  event_type: string | null;
}

export interface HypothesisItem {
  id: string;
  title: string;
  description: string | null;
  status: string;
  confidence: number | null;
}

export interface SuggestedActionItem {
  id: string;
  title: string;
  description: string | null;
  action_type: string | null;
  status: string;
  requires_human_approval: boolean;
}

export interface AlertItem {
  id: string;
  source: string;
  title: string;
  description: string | null;
  status: string;
  severity: string | null;
  fired_at: string | null;
}

export interface ImpactItem {
  id: string;
  impact_type: string;
  description: string | null;
  severity: string | null;
  affected_services: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
}

export interface PostmortemSummary {
  id: string;
  title: string;
  status: string;
  postmortem_source: string;
  sections: Record<string, unknown> | null;
  created_at: string;
}

export interface IncidentWorkspace {
  incident: Incident;
  alerts: AlertItem[];
  runs: InvestigationRun[];
  run: InvestigationRunDetail | null;
  evidence: EvidenceItem[];
  timeline: TimelineItem[];
  hypotheses: HypothesisItem[];
  suggested_actions: SuggestedActionItem[];
  impacts: ImpactItem[];
  postmortem: PostmortemSummary | null;
}

export async function getIncidentWorkspace(
  incidentId: string,
  runId?: string
): Promise<IncidentWorkspace> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const response = await apiFetch(`/api/incidents/${incidentId}/workspace${query}`);
  if (!response.ok) throw await toError(response);
  return (await response.json()) as IncidentWorkspace;
}

export async function startInvestigation(
  incidentId: string
): Promise<InvestigationRun> {
  const response = await apiFetch(
    `/api/incidents/${incidentId}/investigation-runs`,
    { method: "POST" }
  );
  if (!response.ok) throw await toError(response);
  return (await response.json()) as InvestigationRun;
}

export async function getInvestigationRun(
  runId: string
): Promise<InvestigationRunDetail> {
  const response = await apiFetch(`/api/investigation-runs/${runId}`);
  if (!response.ok) throw await toError(response);
  return (await response.json()) as InvestigationRunDetail;
}

export const TERMINAL_RUN_STATUSES = ["completed", "failed"] as const;

export function isTerminalRunStatus(status: string): boolean {
  return (TERMINAL_RUN_STATUSES as readonly string[]).includes(status);
}

// --- Knowledge ----------------------------------------------------------------

export interface KnowledgeGraph {
  services: { id: string; name: string; service_type: string | null; description: string | null }[];
  dependencies: {
    id: string;
    upstream_name: string;
    downstream_name: string;
    dependency_type: string | null;
  }[];
  runbooks: { id: string; title: string; content: string | null }[];
}

export interface KnowledgeProposal {
  id: string;
  proposal_type: string;
  status: string;
  confidence: number | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export async function getKnowledgeGraph(): Promise<KnowledgeGraph> {
  const response = await apiFetch("/api/knowledge/graph");
  if (!response.ok) throw await toError(response);
  return (await response.json()) as KnowledgeGraph;
}

export async function listKnowledgeProposals(): Promise<KnowledgeProposal[]> {
  const response = await apiFetch("/api/knowledge/proposals");
  if (!response.ok) throw await toError(response);
  return (await response.json()) as KnowledgeProposal[];
}

// --- Integrations -------------------------------------------------------------

export interface IntegrationProvider {
  provider: string;
  configured: boolean;
}

export interface IntegrationsStatus {
  connections: { id: string; provider: string; name: string | null; status: string }[];
  providers: IntegrationProvider[];
}

export async function getIntegrations(): Promise<IntegrationsStatus> {
  const response = await apiFetch("/api/integrations");
  if (!response.ok) throw await toError(response);
  return (await response.json()) as IntegrationsStatus;
}

export async function testGithubIntegration(): Promise<{ ok: boolean; detail: string }> {
  const response = await apiFetch("/api/integrations/github/test", { method: "POST" });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as { ok: boolean; detail: string };
}

export async function testRenderIntegration(): Promise<{ ok: boolean; detail: string }> {
  const response = await apiFetch("/api/integrations/render/test", { method: "POST" });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as { ok: boolean; detail: string };
}

// --- Organization settings ----------------------------------------------------

export interface OrganizationSettings {
  id: string;
  timezone: string;
  default_severity: string | null;
  preferences: Record<string, unknown> | null;
  notes: string | null;
}

export interface OrganizationMember {
  id: string;
  user_id: string;
  role: string;
  status: string;
  created_at: string;
}

export async function getOrganizationSettings(): Promise<OrganizationSettings> {
  const response = await apiFetch("/organizations/settings");
  if (!response.ok) throw await toError(response);
  return (await response.json()) as OrganizationSettings;
}

export async function listOrganizationMembers(): Promise<OrganizationMember[]> {
  const response = await apiFetch("/organizations/members");
  if (!response.ok) throw await toError(response);
  return (await response.json()) as OrganizationMember[];
}

// --- Postmortem ---------------------------------------------------------------

export async function generatePostmortem(
  incidentId: string,
  resolutionNotes?: string
): Promise<PostmortemSummary> {
  const response = await apiFetch(`/api/incidents/${incidentId}/postmortem`, {
    method: "POST",
    body: JSON.stringify({ resolution_notes: resolutionNotes ?? null }),
  });
  if (!response.ok) throw await toError(response);
  const body = (await response.json()) as { postmortem: PostmortemSummary };
  return body.postmortem;
}
