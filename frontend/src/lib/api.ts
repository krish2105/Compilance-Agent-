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

export async function login(username: string, password: string): Promise<{
  token: string;
  user: { username: string; role: "analyst" | "mlro" | "admin" };
}> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
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
