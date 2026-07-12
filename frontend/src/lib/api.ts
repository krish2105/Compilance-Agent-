// Thin API client for the ComplianceAgent backend.
// The API key is attached to every request as the X-API-Key header.

import type {
  AuditEvent,
  CaseSummary,
  InvestigationResult,
  ReviewRecord,
} from "./types";

const API_URL = (import.meta.env.VITE_API_URL as string) || "http://127.0.0.1:8099";
const API_KEY = (import.meta.env.VITE_API_KEY as string) || "dev-local-key";

export const apiConfig = { API_URL, API_KEY };

/** Auth header: a logged-in user's JWT, else the demo X-API-Key. */
export function authHeader(): Record<string, string> {
  let token: string | null = null;
  try {
    token = localStorage.getItem("ca-token");
  } catch {
    /* ignore */
  }
  return token ? { Authorization: `Bearer ${token}` } : { "X-API-Key": API_KEY };
}

function headers(json = false): HeadersInit {
  const h: Record<string, string> = { ...authHeader() };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

export interface AuthResponse {
  token: string;
  user: { username: string; role: "analyst" | "mlro" | "admin" };
  tenant?: { slug: string; name: string };
}

export async function login(
  username: string,
  password: string,
  org = "demo",
): Promise<AuthResponse> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, org }),
  });
  return handle(res);
}

/** Ingest transactions as JSON rows → creates a tenant case. */
export async function ingestRows(
  rows: Record<string, unknown>[],
  summary?: string,
): Promise<{ ok: boolean; case: { case_id: string; priority: string; transaction_count: number } }> {
  const res = await fetch(`${API_URL}/api/ingest/transactions`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify({ rows, summary }),
  });
  return handle(res);
}

/** Ingest a CSV file upload → creates a tenant case. */
export async function ingestCsv(
  file: File,
): Promise<{ ok: boolean; case: { case_id: string; priority: string; transaction_count: number } }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/ingest/csv`, {
    method: "POST",
    headers: authHeader(), // no Content-Type — browser sets multipart boundary
    body: form,
  });
  return handle(res);
}

export const ingestTemplateUrl = `${API_URL}/api/ingest/template`;

export interface BillingInfo {
  plan: string;
  limits: { label: string; price_usd: number; max_members: number | null; max_uploaded_cases: number | null };
  usage: { members: number; uploaded_cases: number };
  plans: Record<string, { label: string; price_usd: number; max_members: number | null; max_uploaded_cases: number | null }>;
}

/** Current plan, limits and usage for the caller's org. */
export async function getBilling(): Promise<BillingInfo> {
  const res = await fetch(`${API_URL}/api/auth/billing`, { headers: headers() });
  return handle<BillingInfo>(res);
}

/** Change the org plan (admin). */
export async function changePlan(plan: string): Promise<{ ok: boolean; plan: string; billing: BillingInfo }> {
  const res = await fetch(`${API_URL}/api/auth/billing/plan`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify({ plan }),
  });
  return handle(res);
}

/** Rename the organization's display name (admin). */
export async function renameOrg(name: string): Promise<{ ok: boolean; tenant: { slug: string; name: string } }> {
  const res = await fetch(`${API_URL}/api/auth/org`, {
    method: "PATCH",
    headers: headers(true),
    body: JSON.stringify({ name }),
  });
  return handle(res);
}

/** Download a case's audit trail as CSV (with auth). */
export async function downloadAuditCsv(caseId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/audit.csv`, { headers: headers() });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audit_${caseId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export interface TeamMember {
  username: string;
  email: string;
  full_name: string;
  role: "analyst" | "mlro" | "admin";
  active: boolean;
}

/** List members of the caller's organization (admin only). */
export async function listUsers(): Promise<TeamMember[]> {
  const res = await fetch(`${API_URL}/api/auth/users`, { headers: headers() });
  return handle<TeamMember[]>(res);
}

/** Add a member to the caller's organization (admin only). */
export async function addUser(payload: {
  username: string;
  password: string;
  role: string;
  email?: string;
  full_name?: string;
}): Promise<{ ok: boolean; user: TeamMember }> {
  const res = await fetch(`${API_URL}/api/auth/register`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify(payload),
  });
  return handle(res);
}

/** Self-service password change. Returns a fresh token (old sessions are revoked). */
export async function changePassword(
  oldPassword: string,
  newPassword: string,
): Promise<{ ok: boolean; token: string }> {
  const res = await fetch(`${API_URL}/api/auth/change-password`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
  return handle(res);
}

/** Change a member's role, active status, or reset their password (admin only). */
export async function updateUser(
  username: string,
  patch: { role?: string; active?: boolean; password?: string },
): Promise<{ ok: boolean; user: TeamMember }> {
  const res = await fetch(`${API_URL}/api/auth/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    headers: headers(true),
    body: JSON.stringify(patch),
  });
  return handle(res);
}

/** Public self-serve onboarding — create a new organization + its first admin user. */
export async function registerOrg(payload: {
  org_name: string;
  username: string;
  password: string;
  email?: string;
  full_name?: string;
}): Promise<AuthResponse> {
  const res = await fetch(`${API_URL}/api/auth/register-org`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      msg = body.message || body.detail || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth() {
  const res = await fetch(`${API_URL}/api/health`);
  return handle<Record<string, unknown>>(res);
}

export async function listCases(): Promise<CaseSummary[]> {
  const res = await fetch(`${API_URL}/api/cases`, { headers: headers() });
  return handle<CaseSummary[]>(res);
}

export async function getCaseDetail(caseId: string): Promise<{
  case: CaseSummary;
  result: InvestigationResult;
  review: ReviewRecord | null;
  review_history: ReviewRecord[];
}> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}`, { headers: headers() });
  return handle(res);
}

export async function investigate(caseId: string): Promise<InvestigationResult> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/investigate`, {
    method: "POST",
    headers: headers(),
  });
  return handle<InvestigationResult>(res);
}

export async function getAudit(
  caseId: string,
): Promise<{ case_id: string; events: AuditEvent[]; reviews: ReviewRecord[] }> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/audit`, { headers: headers() });
  return handle(res);
}

export interface ReviewPayload {
  decision: "APPROVED" | "REJECTED" | "EDITED" | "ESCALATED";
  reviewer: string;
  notes?: string;
  edited_narrative?: string;
}

export async function submitReview(caseId: string, payload: ReviewPayload) {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/review`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify(payload),
  });
  return handle<{ ok: boolean; review: ReviewRecord }>(res);
}

/** URL used by the SSE hook (EventSource can't set headers, so the key is a query param). */
export function streamUrl(caseId: string): string {
  return `${API_URL}/api/cases/${caseId}/stream`;
}

/**
 * Portfolio analytics.
 *
 * Primary path: the backend `/api/dashboard` endpoint (richer — includes ensemble
 * risk bands, typology mix and screening hit-rate). If that endpoint is unavailable
 * (e.g. the backend hasn't picked up the latest deploy, or a cold-start timeout),
 * we transparently fall back to computing the core analytics client-side from the
 * case queue — so the dashboard is *always* populated, never a dead error screen.
 */
export async function getDashboard(): Promise<Record<string, any>> {
  try {
    // Bound the server call — the ensemble assessment can be slow on a cold free-tier
    // instance; if it doesn't answer quickly we fall back rather than hang the page.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12_000);
    let res: Response;
    try {
      res = await fetch(`${API_URL}/api/dashboard`, { headers: headers(), signal: ctrl.signal });
    } finally {
      clearTimeout(timer);
    }
    if (res.ok) {
      const data = (await res.json()) as Record<string, any>;
      return { ...data, source: "server" };
    }
    throw new Error(String(res.status));
  } catch {
    // Graceful degradation — compute from the case book (always available & fast).
    const cases = await listCases();
    return computeClientDashboard(cases);
  }
}

/** Client-side analytics from the case queue (used when the server endpoint is unavailable). */
function computeClientDashboard(cases: CaseSummary[]): Record<string, any> {
  const n = cases.length;
  const inc = (o: Record<string, number>, k: string) => (o[k] = (o[k] ?? 0) + 1);

  const by_priority: Record<string, number> = {};
  const dispositions: Record<string, number> = {};
  let pending = 0;
  let finalized = 0;
  let totalTx = 0;

  for (const c of cases) {
    inc(by_priority, c.priority ?? "Medium");
    const status = c.review_status || "PENDING_REVIEW";
    inc(dispositions, status);
    if (status === "PENDING_REVIEW") pending += 1;
    if (status.startsWith("APPROVED") || status.startsWith("ESCALATED")) finalized += 1;
    totalTx += c.transaction_count ?? 0;
  }

  const critical_high = (by_priority.Critical ?? 0) + (by_priority.High ?? 0);
  // Priority is the alert's own risk grade — a faithful proxy for the risk posture
  // when the server-side ensemble assessment isn't reachable.
  const order = ["Critical", "High", "Medium", "Low"];
  const risk_bands: Record<string, number> = {};
  for (const k of order) if (by_priority[k]) risk_bands[k] = by_priority[k];

  return {
    source: "client",
    total_cases: n,
    by_priority,
    dispositions,
    risk_bands,
    pending_review: pending,
    critical_high,
    sar_rate: n ? Math.round((finalized / n) * 1000) / 1000 : 0,
    total_transactions: totalTx,
    avg_transactions: n ? Math.round(totalTx / n) : 0,
    reviewed: n - pending,
    top_typologies: [],
    screening_hit_rate: null,
  };
}

/** Fetch the printable case report (with auth) and open it in a new tab (auto-prints). */
export async function openCaseReport(caseId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/report`, { headers: headers() });
  if (!res.ok) throw new Error(`Report failed: ${res.status}`);
  const htmlText = await res.text();
  const blob = new Blob([htmlText], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export interface ChatAnswer {
  answer: string;
  tools_used: string[];
  planner_intents: string[];
  similar_cases: { case_id: string; typology: string; disposition: string; similarity: number }[];
  llm_provider?: string;
  blocked: boolean;
}

export async function chatWithCase(
  caseId: string,
  question: string,
  history: { role: string; content: string }[],
): Promise<ChatAnswer> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/chat`, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify({ question, history }),
  });
  return handle<ChatAnswer>(res);
}

export async function getSar(caseId: string): Promise<{
  sar: Record<string, unknown>;
  sla: Record<string, unknown>;
  goaml_available: boolean;
}> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/sar`, { headers: headers() });
  return handle(res);
}

/** Fetch the goAML XML (with auth header) and trigger a browser download. */
export async function downloadSarXml(caseId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/cases/${caseId}/sar.xml`, { headers: headers() });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `STR_${caseId}_goAML.xml`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
