# Phase 3 Early Implementation: LangGraph Orchestration & Grounded Generation

## 1. Early Implemented Scope

Phase 3 orchestration and grounded local generation have been implemented ahead of schedule and validated through unit, integration, and guardrail tests in accordance with [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) Sections 1, 2, 4, 11, 14, 15, and 19:

- **State, Action Contracts & Guardrails**:
  - Strict Pydantic v2 `EvidenceOpsState` (`extra="forbid"`) with non-blank query validation, finite float validation, bound checks (`iteration_count <= max_iterations <= 3`, `retrieval_calls <= max_retrieval_calls <= 3`), terminal invariants (`COMPLETED` requires non-empty answer; `ABSTAINED` requires non-empty reason), and bidirectional dictionary adapters (`to_langgraph_dict()`, `from_langgraph_dict()`).
  - Canonical `AbstentionReason` enum covering evidence thresholds, conflict, budget exhaustion, duplicate reformulation, and generator/retrieval failures.
  - Domain error hierarchy (`EvidenceOpsError`, `StateTransitionError`, `GuardrailViolationError`, `GenerationError`, `OllamaUnavailableError`, `OllamaTimeoutError`, `CitationValidationError`).

- **Query Features & Heuristic Controller**:
  - `RegexFeatureExtractor` extracting syntactic, structural, and domain features (token counts, code terms, comparison, temporal, multi-hop, subquestions, entity counts, greeting detection).
  - Deterministic `HeuristicRetrievalController` executing ordered, transparent heuristic rules without LLM dependencies. Every decision outputs an actionable `Action`, optional `QueryRoute`, confidence, and transparent `reason_code`.

- **Evidence Processing, Context Packing, Sufficiency & Conflict**:
  - `adapt_retrieval_results`: Adapts raw `RetrievalResult` objects into `EvidenceRecord` items, deduplicating chunk IDs, merging retrieval routes, and retaining best rank/score.
  - `pack_evidence_context`: Bounded context packing enforcing hard limits (max 6 chunks, max 24,000 characters), preserving chunk boundaries with provenance, and delimiting evidence with untrusted-data boundaries.
  - `evaluate_sufficiency`: Non-LLM composite sufficiency formula:
    $$S = 0.45R + 0.25C + 0.15D + 0.15A$$
    Where $R$ is normalized relevance, $C$ is query token coverage, $D$ is document diversity, and $A$ is answerability heuristic syntax.
  - `detect_evidence_conflicts`: Conservative pairwise contradiction detection (differing numeric values for identical attributes and direct boolean support contradictions).

- **Ollama Client, Grounded Prompting & Citation Validation**:
  - Local `OllamaClient` targeting `/v1/chat/completions` at `temperature=0.0` with connection timeout handling and structured error mapping.
  - Prompt builders (`build_grounded_prompt`, `build_direct_answer_prompt`, `build_citation_correction_prompt`) enforcing strict grounding instructions and prohibition of external knowledge.
  - Citation verification (`assign_citations`, `extract_inline_citations`, `validate_answer_citations`): Verifies that all inline citations (`[C1]`, `[C2]`, ...) match real retrieved evidence.
  - `LocalQueryReformulator`: Deterministic alternative query generation preserving exact code terms and rejecting duplicate queries across attempts.

- **Bounded LangGraph Workflow & Service**:
  - Compiled LangGraph `StateGraph(GraphState)` connecting 11 discrete nodes (`initialize`, `extract_features`, `controller_decide`, `retrieve`, `rerank`, `evaluate_evidence`, `reformulate`, `generate`, `validate_citations`, `abstain`, `finalize`).
  - Conditional routing edges enforcing resource ceilings and cycle limits: maximum 3 retrieval calls, maximum 3 reformulation iterations, and at most 1 citation correction retry before explicit abstention.
  - `QueryService` facade exposing `execute_query(request: QueryRequest) -> QueryResponse`.

- **CLI & Integration**:
  - `evidenceops-query` command line interface supporting positional and `--query` flags, `--require-citations`, `--max-retrieval-calls`, `--max-iterations`, `--temperature`, and `--json` output.
  - Integration test suites covering end-to-end grounded query execution, citation verification, deterministic abstention, query reformulation recovery, and service fallback.

---

## 2. Public Interfaces and Contracts

Downstream subsystems interact through public contracts in `evidenceops.graph`:

```python
from evidenceops.graph.service import QueryRequest, QueryResponse, QueryService

service = QueryService(
    sparse_retriever=sparse_retriever,
    dense_retriever=dense_retriever,
    hybrid_retriever=hybrid_retriever,
    reranker=reranker,
    generator_client=generator_client,
)

request = QueryRequest(
    query="How do I declare status codes in FastAPI?",
    max_retrieval_calls=3,
    max_iterations=3,
    require_citations=True,
    temperature=0.0,
)

response: QueryResponse = service.execute_query(request)
```

### Key Request Fields
- `query` (str, 1-1000 chars, non-blank)
- `run_id` (str | None, auto-generated if omitted)
- `max_retrieval_calls` (int, 1-3, default 3)
- `max_iterations` (int, 1-3, default 3)
- `require_citations` (bool, default True)
- `temperature` (float, default 0.0)

### Key Response Fields
- `run_id` (str)
- `status` (`RunStatus`: `COMPLETED` | `ABSTAINED` | `FAILED`)
- `answer` (str | None)
- `citations` (list[str], e.g. `["C1", "C2"]`)
- `abstention_reason` (str | None, e.g. `evidence_below_threshold`, `generator_unavailable`)
- `retrieval_calls` (int, <= 3)
- `iterations` (int, <= 3)
- `sufficiency_score` (float in [0.0, 1.0])
- `conflict_score` (float in [0.0, 1.0])
- `evidence` (list[EvidenceRecord])
- `duration_ms` (float)

---

## 3. Ollama Status & Phase 3 Gates

In accordance with [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) Section 19:
- The local Ollama daemon is reachable at `http://127.0.0.1:11434`.
- Host inspection via `ollama list` confirmed 0 models currently pulled on the developer machine.
- In strict adherence to project rules, no models were pulled automatically during preflight.
- When an approved local model (e.g. `qwen2.5:3b-instruct`) is pulled via `ollama pull qwen2.5:3b-instruct`, running `uv run pytest -m ollama` will execute the live local model smoke test (`test_real_ollama_generation_smoke`).
- Note: Phase 1C manual inspection judgments remain pending human review; no unmeasured retrieval-quality improvements are claimed.
