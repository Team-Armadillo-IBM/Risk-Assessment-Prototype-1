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
