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

## Prerequisites

- Python 3.10 or later (the package relies on modern typing features such as
  `Protocol` and `dataclasses` improvements).
- `pip` 23+ and `setuptools` 65+ for editable installs.
- Access to your institution's policy retrieval system, risk scoring service,
  and governance logging endpoint (the repository provides protocol interfaces
  and stubs, not concrete implementations).

Create and activate a virtual environment before installation to avoid
polluting system packages:

```bash
python -m venv .venv
source .venv/bin/activate
```

## Installation

1. Clone the repository and enter the project directory:

   ```bash
   git clone https://github.com/your-org/Risk-Assessment-Prototype-1.git
   cd Risk-Assessment-Prototype-1
   ```

2. Install the package in editable mode so you can iterate on integrations:

   ```bash
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install -e .
   ```

   The package exposes `loan_risk_assistant` for import in your applications and
   tests. Because the code depends only on the Python standard library, no
   additional runtime dependencies are required by default.

## Configuration

The assistant expects that you provide callables for integration points defined
in `loan_risk_assistant.tools`. In production those callables typically depend
on environment variables or secrets. Common settings include:

- `POLICY_API_BASE_URL` / `POLICY_API_KEY` – used by the policy document
  retriever to connect to your document store or retrieval service.
- `RISK_SCORING_API_URL` / `RISK_SCORING_API_KEY` – consumed by the risk scoring
  client when submitting the payload produced by `LoanRiskAssistant`.
- `GOVERNANCE_LOG_ENDPOINT` / `GOVERNANCE_LOG_TOKEN` – required by the
  governance logger to persist audit events.
- Optional: `INTEREST_POLICY_RESOLVER` configuration if your interest rate
  calculation lives behind another microservice.

Export the relevant environment variables before running the assistant or wire
them through your dependency injection mechanism:

```bash
export POLICY_API_BASE_URL="https://policies.internal/api"
export POLICY_API_KEY="***"
export RISK_SCORING_API_URL="https://risk.internal/score"
export RISK_SCORING_API_KEY="***"
export GOVERNANCE_LOG_ENDPOINT="https://governance.internal/log"
export GOVERNANCE_LOG_TOKEN="***"
```

## Usage

### Run the provided sample

The quickest way to see the assistant in action is to run the example module
that wires stubbed tools together:

```bash
python examples/sample_run.py
```

The script prints the structured response produced by
`LoanRiskAssistant.assess(...)`, including the calculated tier, requested
documents, and policy citations.

### Programmatic usage

Import the package and instantiate `LoanRiskAssistant` with your concrete
implementations. The assistant exposes a single orchestration entry point,
`assess`, which expects a `LoanApplication` dataclass:

```python
from loan_risk_assistant import LoanApplication, LoanRiskAssistant
from integrations import (
    policy_docs_retriever,
    risk_scoring_api,
    get_policy_by_id,
    compose_user_packet,
    request_additional_docs,
    governance_log,
    interest_policy_resolver,
)

assistant = LoanRiskAssistant(
    policy_docs_retriever=policy_docs_retriever,
    risk_scoring_api=risk_scoring_api,
    get_policy_by_id=get_policy_by_id,
    compose_user_packet=compose_user_packet,
    request_additional_docs=request_additional_docs,
    governance_log=governance_log,
    interest_policy_resolver=interest_policy_resolver,
    policy_top_k=5,
)

application = LoanApplication(
    application_id="APP-123",
    borrower={"credit_score": 645, "dti": 0.46},
    loan={"amount": 250_000, "term_months": 60},
    region="CA",
    product="smb_term",
)

assessment = assistant.assess(application)
```

The returned dictionary matches the business specification and can be routed to
case management systems, LOB portals, or downstream analytics.

## Integrating with an agnostic orchestration framework

When embedding the assistant into a broader framework (for example, a Watsonx
agnostic runtime), treat `LoanRiskAssistant.assess` as the primary entry point.
Provide adapters that satisfy the protocols in `loan_risk_assistant.tools`:

| Protocol | Responsibility | Expected signature |
| --- | --- | --- |
| `PolicyDocsRetriever` | Query policy knowledge base | `(query: str, top_k: int) -> List[PolicyChunk]` |
| `RiskScoringAPI` | Submit borrower features to scoring service | `(payload: Dict[str, Any]) -> RiskScoreResult` |
| `GetPolicyById` | Resolve canonical policy metadata | `(ids: Iterable[str]) -> Dict[str, PolicyChunk]` |
| `ComposeUserPacket` | Generate the final customer-facing packet | `(data: Dict[str, Any]) -> Dict[str, Any]` |
| `RequestAdditionalDocs` | Trigger document requests | `(documents: List[str]) -> Dict[str, Any]` |
| `GovernanceLog` | Persist governance/audit events | `(event_type: str, payload: Dict[str, Any]) -> GovernanceLogRecord` |
| `InterestPolicyResolver` *(optional)* | Derive interest bands from policy metadata | `(policy_chunks: List[PolicyChunk], risk_tier: str) -> InterestBand \| None` |

Most agnostic frameworks support dependency registration via configuration. A
minimal YAML snippet that binds the assistant can look like this:

```yaml
risk_assistant:
  class: loan_risk_assistant.agent.LoanRiskAssistant
  init:
    policy_docs_retriever: !ref integrations.policy_retriever
    risk_scoring_api: !ref integrations.risk_client
    get_policy_by_id: !ref integrations.policy_lookup
    compose_user_packet: !ref integrations.packet_builder
    request_additional_docs: !ref integrations.doc_requester
    governance_log: !ref integrations.governance_logger
    interest_policy_resolver: !ref integrations.interest_resolver
```

The framework should call `risk_assistant.assess` with a JSON payload that maps
cleanly onto the `LoanApplication` dataclass. A representative command-line
trigger might look like:

```bash
python -m framework.run --component risk_assistant --input application.json
```

Ensure your framework serialises incoming application data into the
`LoanApplication` fields (borrower profile, loan terms, region, product, and
optional context) before invoking the assistant.

## Testing

Run unit tests after updating integrations or business logic:

```bash
python -m pytest
```

For framework-level smoke tests, feed a fixture application through your
adapter layer and assert on the assistant's JSON response. For example:

```bash
python -m pytest tests -k "integration"
```

When integrating into CI, combine the pytest suite with any framework-specific
contract tests you maintain to validate your adapters and environment
configuration.
