# Risk-Assessment-Prototype-1

Prototype scaffolding for a watsonx-powered loan risk assessment agent. The
package `loan_risk_assistant` coordinates policy retrieval, risk scoring, and
compliance logging into a single `LoanRiskAssistant` class. The class expects
callables for the bank's existing tooling (policy retrieval, risk scoring API,
policy lookup, governance logging, etc.) and returns the structured JSON format
required by the business specification.

## Layout

- `loan_risk_assistant/` – Core package with data models and orchestration
  logic.
- `examples/sample_run.py` – Demonstrates wiring the assistant with stubbed
  tools.
- `tests/` – Pytest coverage for the orchestration behaviour.

## Running the sample

```bash
python examples/sample_run.py
```

## Running tests

```bash
pytest
```

## Integrating with the Agnostic framework

The agnostic orchestration framework expects tools to be registered behind a
JSON-compatible callable signature (`Callable[[Dict[str, Any]], Dict[str, Any]]`)
and agents to be constructed with a runtime-provided tool invoker. The
assistant already defines Python protocols for its dependencies in
`loan_risk_assistant/tools.py`. The table below summarises how those protocols
map to the framework’s expectations and the shape of the adapters provided in
`loan_risk_assistant/agnostic_adapter.py`.

| Assistant protocol | Native signature | Agnostic wrapper | Framework payload contract |
| ------------------- | ---------------- | ---------------- | --------------------------- |
| `PolicyDocsRetriever` | `(query: str, top_k: int) -> List[PolicyChunk]` | `adapt_policy_docs_retriever` | Input: `{ "query": str, "top_k": int }`; Output: `{ "chunks": [...] }` |
| `RiskScoringAPI` | `(payload: Dict[str, Any]) -> RiskScoreResult` | `adapt_risk_scoring_api` | Input: `{ "payload": {...} }`; Output: `{ "score": float, "features": [...], "reason_codes": [...] }` |
| `GetPolicyById` | `(ids: Iterable[str]) -> Dict[str, PolicyChunk]` | `adapt_get_policy_by_id` | Input: `{ "ids": [str] }`; Output: `{ "chunks": [...] }` |
| `ComposeUserPacket` | `(data: Dict[str, Any]) -> Dict[str, Any]` | `adapt_compose_user_packet` | Input: `{ "data": {...} }`; Output: `{ "packet": {...} }` |
| `RequestAdditionalDocs` | `(documents: List[str]) -> Dict[str, Any]` | `adapt_request_additional_docs` | Input: `{ "documents": [str] }`; Output: `{ "request": {...} }` |
| `GovernanceLog` | `(event_type: str, payload: Dict[str, Any]) -> GovernanceLogRecord` | `adapt_governance_log` | Input: `{ "event_type": str, "payload": {...} }`; Output: `{ "log_id": str, ... }` |
| `InterestPolicyResolver` (optional) | `(policy_chunks: List[PolicyChunk], risk_tier: str) -> InterestBand | None` | `adapt_interest_policy_resolver` | Input: `{ "policy_chunks": [...], "risk_tier": str }`; Output: `{ "band": {...} | null }` |

To run the assistant inside the framework you can use
`LoanRiskAgnosticAgent`, which receives the framework’s `invoke_tool(name,
payload)` callback and projects it into the assistant’s dependency graph. The
helper `available_tool_adapters` function exposes the bank-specific
implementations as framework-ready tool registrations.

```python
from agnostic.runtime import Runtime  # framework component
from loan_risk_assistant.agnostic_adapter import (
    LoanRiskAgnosticAgent,
    available_tool_adapters,
)

runtime = Runtime()
tool_adapters = available_tool_adapters(
    policy_docs_retriever=my_policy_retriever,
    risk_scoring_api=my_risk_scoring_api,
    get_policy_by_id=my_policy_lookup,
    compose_user_packet=my_packet_builder,
    request_additional_docs=my_doc_requester,
    governance_log=my_governance_logger,
)
for adapter in tool_adapters:
    runtime.register_tool(adapter.name, adapter.invoke, adapter.input_schema, adapter.output_schema)

agent = LoanRiskAgnosticAgent(runtime.invoke_tool, available_tools=runtime.tool_names)
runtime.set_agent(agent)
response = runtime.run({
    "application_id": "APP-001",
    "borrower": {...},
    "loan": {...},
    "region": "NY",
    "product": "smb_term",
})
```

The smoke test in `tests/test_agnostic_framework_integration.py` demonstrates
the full flow with stubbed tools and validates that the assistant produces the
same response when mediated by the framework runtime.
