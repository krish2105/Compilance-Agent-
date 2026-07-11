// Shared TypeScript types mirroring the backend payloads.

export type Priority = "Critical" | "High" | "Medium" | "Low";

export interface CaseSummary {
  case_id: string;
  created_at: string;
  subject_account: string;
  focal_transaction_id: string;
  alert_summary: string;
  priority: Priority;
  status: string;
  transaction_count: number;
  review_status: string;
  reviewed_by: string | null;
}

export interface Transaction {
  transaction_id: string;
  timestamp: string;
  date: string;
  time: string;
  sender_account: string;
  receiver_account: string;
  amount: number;
  payment_currency: string;
  received_currency: string;
  sender_bank_location: string;
  receiver_bank_location: string;
  payment_type: string;
  is_laundering: number;
  laundering_type: string;
  case_id: string | null;
}

export interface Kyc {
  full_name?: string;
  risk_rating?: string;
  pep_flag?: boolean;
  occupation?: string;
  residence_country?: string;
  source_of_funds?: string;
  expected_monthly_volume_aed?: number;
  kyc_last_review_date?: string;
  account_number?: string;
  [k: string]: unknown;
}

export interface Facts {
  transaction_count: number;
  total_amount: number;
  max_amount: number;
  distinct_senders: number;
  distinct_receivers: number;
  max_fan_out: number;
  max_fan_in: number;
  sub_threshold_count: number;
  cross_border_tx: number;
  sanctioned_jurisdiction: boolean;
  cash_tx: number;
  min_pass_through_minutes: number | null;
  has_cycle: boolean;
  layering_depth: number;
  pep_involved: boolean;
  involved_locations: string[];
  currencies: string[];
  signature: Record<string, number>;
  [k: string]: unknown;
}

export interface TypologyDriver {
  dimension: string;
  contribution: number;
}
export interface TypologyMatch {
  best_match: {
    typology_key: string;
    typology_label: string;
    similarity: number;
    confidence: number;
    drivers: TypologyDriver[];
    definition: string;
    red_flags: string[];
  };
  ranked: {
    typology_key: string;
    typology_label: string;
    similarity: number;
    drivers: TypologyDriver[];
  }[];
  confidence: number;
  rationale: string;
}

export interface VerifiedClaim {
  id: string;
  statement: string;
  fact_path: string;
  expected: unknown;
  actual: unknown;
  verified: boolean;
}
export interface Verification {
  passed: boolean;
  should_retry: boolean;
  issues: { type: string; detail: string; reference?: string }[];
  verified_claims: VerifiedClaim[];
  citations_checked: number;
  fabricated_citations: string[];
  unsupported_figures: string[];
  low_confidence: boolean;
  summary: string;
}

export interface RunMetrics {
  total_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  llm_calls: number;
  providers: string[];
  spans: { name: string; latency_ms: number }[];
  generations: {
    provider: string;
    model: string;
    task: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    latency_ms: number;
  }[];
}

export interface CaseGraph {
  nodes: {
    id: string;
    label: string;
    role: "subject" | "collector" | "distributor";
    in_degree: number;
    out_degree: number;
    x: number;
    y: number;
  }[];
  edges: { source: string; target: string; amount: number; laundering: number; txid: string }[];
  features: Record<string, unknown>;
}

export interface InvestigationResult {
  case_id: string;
  status: string;
  evidence: {
    summary: string;
    facts: Facts;
    subject_kyc: Kyc;
    transactions: Transaction[];
    prior_history: Transaction[];
    counterparty_kyc: Record<string, Kyc>;
    graph?: CaseGraph;
  };
  typology_match: TypologyMatch;
  regulatory: {
    primary: {
      typology_key: string;
      label: string;
      definition: string;
      red_flags: string[];
      regulatory_note: string;
    };
    retrieved: {
      chunk_id?: string;
      typology_key: string;
      label: string;
      section?: string;
      text: string;
      rank?: number;
    }[];
    rag_backend: string;
    rag_meta?: Record<string, unknown>;
  };
  narrative: string;
  claims: { id: string; statement: string }[];
  citations: string[];
  llm_provider: string;
  llm_fallback_used: boolean;
  verification: Verification;
  metrics?: RunMetrics;
  error?: string;
}

export interface AgentStepEvent {
  type: "agent_step";
  agent: string;
  step: number;
  status: "running" | "done" | "error" | "retry";
  title: string;
  detail: Record<string, unknown>;
  ts: number;
}

export interface AuditEvent {
  id: number;
  case_id: string;
  ts: string;
  actor: string;
  actor_type: string;
  action: string;
  summary: string | null;
  detail: Record<string, unknown>;
  llm_provider: string | null;
}

export interface ReviewRecord {
  case_id: string;
  ts: string;
  decision: string;
  reviewer: string;
  notes: string | null;
  status: string;
}
