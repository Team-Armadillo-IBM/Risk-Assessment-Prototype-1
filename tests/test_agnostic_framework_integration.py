from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Sequence

import pytest

from loan_risk_assistant.agnostic_adapter import (
    LoanRiskAgnosticAgent,
    available_tool_adapters,
)
from loan_risk_assistant.models import (
    GovernanceLogRecord,
    PolicyChunk,
    ReasonCode,
    RiskFeature,
    RiskScoreResult,
)


@dataclass
class FrameworkTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    call_count: int = 0

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.call_count += 1
        return self.handler(payload)


class FrameworkRuntime:
    def __init__(self, tools: Sequence[FrameworkTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._agent: LoanRiskAgnosticAgent | None = None

    @property
    def tool_names(self) -> Iterable[str]:
        return self._tools.keys()

    def register_agent(self, agent: LoanRiskAgnosticAgent) -> None:
        self._agent = agent

    def invoke_tool(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        return self._tools[name].invoke(payload)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._agent is None:
            raise RuntimeError("Agent not registered")
        return self._agent.run(payload)


@pytest.fixture()
def bank_tools() -> Dict[str, Callable]:
    def _policy_retriever(query: str, top_k: int = 5) -> List[PolicyChunk]:
        metadata = {
            "guidance": "Documented collateral required",
            "interest_band": {
                "min_apr": 6.0,
                "max_apr": 8.5,
                "policy_reference": "POL-APR-01",
                "conditions": ["Manual review"],
            },
            "required_documents": ["Collateral appraisal report"],
        }
        chunk = PolicyChunk(
            chunk_id="chunk-xyz",
            title="SMB Lending Policy",
            section="3.1",
            text="Loans flagged as medium risk must document collateral and may carry 6%-8.5% APR.",
            metadata=metadata,
        )
        return [chunk for _ in range(min(top_k, 1))]

    def _risk_scoring_api(payload: Dict[str, Any]) -> RiskScoreResult:
        borrower = payload.get("borrower", {})
        features = [
            RiskFeature(
                code="CREDIT_SCORE",
                description="Credit score below internal target",
                value=borrower.get("credit_score", 0),
                direction="increase",
                weight=0.21,
            )
        ]
        reason_codes = [
            ReasonCode(code="CREDIT_SCORE", description="Credit score below target"),
        ]
        return RiskScoreResult(score=55.0, features=features, reason_codes=reason_codes)

    def _get_policy_by_id(ids: Iterable[str]) -> Dict[str, PolicyChunk]:
        return {
            chunk_id: PolicyChunk(
                chunk_id=chunk_id,
                title="SMB Lending Policy (canonical)",
                section="3.1",
                text="Loans flagged as medium risk must document collateral and may carry 6%-8.5% APR.",
                metadata={},
            )
            for chunk_id in ids
        }

    def _compose_user_packet(data: Dict[str, Any]) -> Dict[str, Any]:
        return {"format": "html", "payload": data}

    def _request_additional_docs(documents: List[str]) -> Dict[str, Any]:
        return {"requested": documents, "crm_ticket": "CRM-12345"}

    class _GovernanceLogger:
        def __init__(self) -> None:
            self.events: List[Dict[str, Any]] = []

        def __call__(self, event_type: str, payload: Dict[str, Any]) -> GovernanceLogRecord:
            self.events.append({"event_type": event_type, "payload": payload})
            return GovernanceLogRecord(event_type=event_type, log_id=f"log-{len(self.events)}")

    return {
        "policy_docs_retriever": _policy_retriever,
        "risk_scoring_api": _risk_scoring_api,
        "get_policy_by_id": _get_policy_by_id,
        "compose_user_packet": _compose_user_packet,
        "request_additional_docs": _request_additional_docs,
        "governance_log": _GovernanceLogger(),
    }


def _materialise_framework_tools(tools: Dict[str, Callable]) -> List[FrameworkTool]:
    adapters = available_tool_adapters(
        policy_docs_retriever=tools["policy_docs_retriever"],
        risk_scoring_api=tools["risk_scoring_api"],
        get_policy_by_id=tools["get_policy_by_id"],
        compose_user_packet=tools["compose_user_packet"],
        request_additional_docs=tools["request_additional_docs"],
        governance_log=tools["governance_log"],
    )
    framework_tools: List[FrameworkTool] = []
    for adapter in adapters:
        framework_tools.append(
            FrameworkTool(
                name=adapter.name,
                description=adapter.description,
                input_schema=adapter.input_schema,
                output_schema=adapter.output_schema,
                handler=adapter.invoke,
            )
        )
    return framework_tools


def test_agnostic_runtime_smoke(bank_tools: Dict[str, Callable]) -> None:
    framework_tools = _materialise_framework_tools(bank_tools)
    runtime = FrameworkRuntime(framework_tools)
    agent = LoanRiskAgnosticAgent(runtime.invoke_tool, available_tools=runtime.tool_names)
    runtime.register_agent(agent)

    payload = {
        "application_id": "APP-001",
        "borrower": {"credit_score": 610, "income_verified": False},
        "loan": {"collateral_required": True},
        "region": "NY",
        "product": "smb_term",
    }

    response = runtime.run(payload)

    assert response["risk_score"]["value"] == pytest.approx(55.0)
    assert response["risk_score"]["tier"] == "Med"
    assert response["interest_rate_suggestion"]["band_apr_percent"] == [6.0, 8.5]
    assert "Collateral ownership evidence" in response["requested_documents"]
    assert "Collateral appraisal report" in response["requested_documents"]
    assert response["governance_log_ids"]

    invocation_counts = {tool.name: tool.call_count for tool in framework_tools}
    assert invocation_counts["policy_docs_retriever"] >= 1
    assert invocation_counts["risk_scoring_api"] >= 1
    assert invocation_counts["compose_user_packet"] >= 1
