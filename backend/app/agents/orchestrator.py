"""
LangGraph Orchestrator.

Models the full investigation flow (Section 5 of the spec) as an explicit state
machine with conditional edges and a retry path on verification failure:

    evidence → typology → regulatory → narrative → verifier
                                          ▲            │
                                          └──retry─────┤ (if hallucination found,
                                                       │  re-draft deterministically)
                                                       ▼
                                                    finalize → END

Every node:
  * emits a structured step event (consumed by the SSE stream for live reasoning),
  * writes a persistent audit-log entry,
  * returns a partial state update.

The graph is compiled once and reused. `run_case_events()` streams the per-step
events; `run_case()` runs to completion and returns the final result.
"""
from __future__ import annotations

import operator
import time
from typing import Annotated, Any, Dict, Generator, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import (
    evidence_agent,
    narrative_agent,
    regulatory_context_agent,
    typology_match_agent,
    verifier,
)
from app.tools import audit

MAX_RETRIES = 1


class AgentState(TypedDict, total=False):
    case_id: str
    evidence: Dict[str, Any]
    typology_match: Dict[str, Any]
    regulatory: Dict[str, Any]
    narrative_result: Dict[str, Any]
    verification: Dict[str, Any]
    retry_count: int
    force_offline: bool
    do_retry: bool
    error: Optional[str]
    events: Annotated[List[Dict[str, Any]], operator.add]


def _event(agent: str, step: int, status: str, title: str,
           detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "type": "agent_step",
        "agent": agent,
        "step": step,
        "status": status,          # 'running' | 'done' | 'error' | 'retry'
        "title": title,
        "detail": detail or {},
        "ts": time.time(),
    }


# --------------------------------------------------------------------- nodes --
def evidence_node(state: AgentState) -> AgentState:
    case_id = state["case_id"]
    try:
        evidence = evidence_agent.gather_evidence(case_id)
    except evidence_agent.EvidenceError as exc:
        audit.log_event(case_id, "EvidenceAgent", "EVIDENCE_ERROR",
                        actor_type="system", summary=str(exc))
        return {"error": str(exc),
                "events": [_event("EvidenceAgent", 1, "error", "Evidence assembly failed",
                                  {"error": str(exc)})]}
    audit.log_event(
        case_id, "EvidenceAgent", "GATHER_EVIDENCE",
        summary=evidence["evidence_summary"],
        detail={"transaction_count": evidence["facts"]["transaction_count"],
                "subject": evidence["subject_account"],
                "total_amount": evidence["facts"]["total_amount"]},
    )
    return {
        "evidence": evidence,
        "events": [_event("EvidenceAgent", 1, "done",
                          "Gathered case evidence from DuckDB",
                          {"summary": evidence["evidence_summary"],
                           "facts": evidence["facts"],
                           "transaction_count": evidence["facts"]["transaction_count"]})],
    }


def typology_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return {}
    case_id = state["case_id"]
    match = typology_match_agent.match_typology(state["evidence"])
    audit.log_event(
        case_id, "TypologyMatchAgent", "MATCH_TYPOLOGY",
        summary=match["rationale"],
        detail={"best": match["best_match"]["typology_key"],
                "confidence": match["confidence"],
                "ranked": [r["typology_key"] for r in match["ranked"]]},
    )
    return {
        "typology_match": match,
        "events": [_event("TypologyMatchAgent", 2, "done",
                          f"Matched typology: {match['best_match']['typology_label']}",
                          {"best_match": match["best_match"],
                           "ranked": match["ranked"],
                           "confidence": match["confidence"],
                           "rationale": match["rationale"]})],
    }


def regulatory_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return {}
    case_id = state["case_id"]
    reg = regulatory_context_agent.get_regulatory_context(state["typology_match"])
    audit.log_event(
        case_id, "RegulatoryContextAgent", "RAG_LOOKUP",
        summary=f"Retrieved regulatory context for {reg['primary']['label']} "
                f"via {reg['rag_backend']}.",
        detail={"typology": reg["primary"]["typology_key"],
                "retrieved": [r["typology_key"] for r in reg["retrieved"]]},
    )
    return {
        "regulatory": reg,
        "events": [_event("RegulatoryContextAgent", 3, "done",
                          f"Retrieved regulatory context ({reg['primary']['label']})",
                          {"primary": reg["primary"], "retrieved": reg["retrieved"],
                           "rag_backend": reg["rag_backend"]})],
    }


def narrative_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return {}
    case_id = state["case_id"]
    force_offline = bool(state.get("force_offline"))
    result = narrative_agent.draft_narrative(
        state["evidence"], state["typology_match"], state["regulatory"],
        force_offline=force_offline,
    )
    audit.log_event(
        case_id, "NarrativeAgent", "DRAFT_NARRATIVE",
        summary=f"Drafted case narrative ({len(result['claims'])} verifiable claims).",
        detail={"provider": result["llm_provider"],
                "fallback_used": result["llm_fallback_used"],
                "claims": len(result["claims"]),
                "force_offline": force_offline},
        llm_provider=result["llm_provider"],
    )
    title = ("Re-drafted narrative deterministically (retry)" if force_offline
             else "Drafted case narrative & EDD report")
    return {
        "narrative_result": result,
        "events": [_event("NarrativeAgent", 4, "done", title,
                          {"provider": result["llm_provider"],
                           "model": result["llm_model"],
                           "fallback_used": result["llm_fallback_used"],
                           "claim_count": len(result["claims"]),
                           "citation_count": len(result["citations"])})],
    }


def verifier_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return {}
    case_id = state["case_id"]
    v = verifier.verify_narrative(
        state["evidence"], state["narrative_result"], state["typology_match"]
    )
    retry = state.get("retry_count", 0)
    will_retry = v["should_retry"] and retry < MAX_RETRIES
    audit.log_event(
        case_id, "Verifier", "VERIFY_NARRATIVE",
        summary=v["summary"],
        detail={"passed": v["passed"], "issues": v["issues"],
                "will_retry": will_retry, "retry_count": retry},
    )
    status = "retry" if will_retry else ("done" if v["passed"] else "done")
    title = ("Verification found unsupported content — triggering deterministic retry"
             if will_retry else
             ("Verification passed — all claims trace to evidence" if v["passed"]
              else "Verification complete — issues flagged for human review"))
    updates: AgentState = {
        "verification": v,
        "do_retry": will_retry,
        "events": [_event("Verifier", 5, status, title,
                          {"passed": v["passed"], "summary": v["summary"],
                           "issues": v["issues"],
                           "verified_claims": v["verified_claims"],
                           "low_confidence": v["low_confidence"]})],
    }
    if will_retry:
        updates["retry_count"] = retry + 1
        updates["force_offline"] = True
    return updates


def finalize_node(state: AgentState) -> AgentState:
    case_id = state["case_id"]
    if state.get("error"):
        audit.log_event(case_id, "Orchestrator", "PIPELINE_ABORTED",
                        actor_type="system", summary=state["error"])
        return {"events": [_event("Orchestrator", 6, "error",
                                  "Pipeline aborted", {"error": state["error"]})]}
    audit.log_event(
        case_id, "Orchestrator", "PIPELINE_COMPLETE",
        actor_type="system",
        summary="Draft ready for human approval gate.",
        detail={"verification_passed": state["verification"]["passed"]},
    )
    return {"events": [_event("Orchestrator", 6, "done",
                              "Draft ready — awaiting human approval",
                              {"verification_passed": state["verification"]["passed"],
                               "awaiting_human_review": True})]}


# --------------------------------------------------------------------- edges --
def _after_evidence(state: AgentState) -> str:
    return "finalize" if state.get("error") else "match_typology"


def _after_verifier(state: AgentState) -> str:
    # `do_retry` is set by the verifier node ONLY while retry_count < MAX_RETRIES,
    # so this is strictly bounded and cannot loop indefinitely.
    return "draft_narrative" if state.get("do_retry") else "finalize"


_compiled = None


def build_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    g = StateGraph(AgentState)
    g.add_node("gather_evidence", evidence_node)
    g.add_node("match_typology", typology_node)
    g.add_node("regulatory_context", regulatory_node)
    g.add_node("draft_narrative", narrative_node)
    g.add_node("verify", verifier_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "gather_evidence")
    g.add_conditional_edges("gather_evidence", _after_evidence,
                            {"match_typology": "match_typology", "finalize": "finalize"})
    g.add_edge("match_typology", "regulatory_context")
    g.add_edge("regulatory_context", "draft_narrative")
    g.add_edge("draft_narrative", "verify")
    g.add_conditional_edges("verify", _after_verifier,
                            {"draft_narrative": "draft_narrative", "finalize": "finalize"})
    g.add_edge("finalize", END)

    _compiled = g.compile()
    return _compiled


# ------------------------------------------------------------------ runners --
def run_case_events(case_id: str) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
    """Stream per-step events as the graph executes; return the final state.

    Yields event dicts (for SSE). The final aggregated result is available via the
    generator's return value and also emitted as a terminal 'result' event by the
    API layer.
    """
    graph = build_graph()
    init: AgentState = {"case_id": case_id, "retry_count": 0, "force_offline": False,
                        "events": []}
    audit.log_event(case_id, "Orchestrator", "PIPELINE_START", actor_type="system",
                    summary=f"Investigation pipeline started for {case_id}.")
    final_state: AgentState = {}
    for update in graph.stream(init, stream_mode="updates"):
        for _node_name, delta in update.items():
            if not delta:
                continue
            final_state.update(delta)
            for ev in delta.get("events", []):
                yield ev
    return final_state


def run_case(case_id: str) -> Dict[str, Any]:
    """Run the pipeline to completion (non-streaming) and return the full result."""
    graph = build_graph()
    init: AgentState = {"case_id": case_id, "retry_count": 0, "force_offline": False,
                        "events": []}
    audit.log_event(case_id, "Orchestrator", "PIPELINE_START", actor_type="system",
                    summary=f"Investigation pipeline started for {case_id}.")
    final = graph.invoke(init)
    return assemble_result(case_id, final)


def assemble_result(case_id: str, state: AgentState) -> Dict[str, Any]:
    """Shape the final graph state into the API/UI result payload."""
    if state.get("error"):
        return {"case_id": case_id, "error": state["error"], "status": "ERROR"}
    return {
        "case_id": case_id,
        "status": "AWAITING_HUMAN_REVIEW",
        "evidence": {
            "summary": state["evidence"]["evidence_summary"],
            "facts": state["evidence"]["facts"],
            "subject_kyc": state["evidence"]["subject_kyc"],
            "transactions": state["evidence"]["transactions"],
            "prior_history": state["evidence"]["prior_history"],
            "counterparty_kyc": state["evidence"]["counterparty_kyc"],
        },
        "typology_match": state["typology_match"],
        "regulatory": state["regulatory"],
        "narrative": state["narrative_result"]["narrative"],
        "claims": state["narrative_result"]["claims"],
        "citations": state["narrative_result"]["citations"],
        "llm_provider": state["narrative_result"]["llm_provider"],
        "llm_fallback_used": state["narrative_result"]["llm_fallback_used"],
        "verification": state["verification"],
        "events": state.get("events", []),
    }
