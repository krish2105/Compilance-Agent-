# Architecture Decision Records (ADRs)

Short, dated records of the *why* behind the significant choices. Format: Context →
Decision → Consequences. (Narrative rationale also in [`../../DECISIONS.md`](../../DECISIONS.md).)

| # | Decision | Status |
|---|---|---|
| [001](001-multi-agent-orchestration.md) | Deterministic multi-agent state machine (LangGraph), not one mega-prompt | Accepted |
| [002](002-from-scratch-gnn.md) | Graph neural network from scratch in NumPy (no PyTorch) | Accepted |
| [003](003-provider-agnostic-llm.md) | Provider-agnostic LLM with an offline fallback (run at $0) | Accepted |
| [004](004-multi-tenancy.md) | Case-id-routed multi-tenancy with a shared demo book | Accepted |
| [005](005-real-sanctions-data.md) | Ship a real committed OFAC/UN snapshot + blocking index | Accepted |
| [006](006-dependency-free-embedder.md) | Stronger n-gram embedder as the $0 default (not sentence-transformers) | Accepted |
