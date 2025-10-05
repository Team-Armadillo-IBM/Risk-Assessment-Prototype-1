from __future__ import annotations

from typing import Dict, List

import pytest

from loan_risk_assistant import (
    GovernanceLogRecord,
    LoanApplication,
    LoanRiskAssistant,
    PolicyChunk,
    ReasonCode,
    RiskFeature,
    RiskScoreResult,
)


@pytest.fixture()
def assistant() -> LoanRiskAssistant:
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
        return [
            PolicyChunk(
                chunk_id="chunk-xyz",
                title="SMB Lending Policy",
                section="3.1",
                text="Loans flagged as medium risk must document collateral and may carry 6%-8.5% APR.",
                metadata=metadata,
            )
        ]

    def _risk_scoring_api(payload: Dict[str, object]) -> RiskScoreResult:
        features = [
            RiskFeature(
                code="CREDIT_SCORE",
                description="Credit score below internal target",
                value=payload["borrower"].get("credit_score", 0),
                direction="increase",
                weight=0.21,
            )
        ]
        reason_codes = [
            ReasonCode(code="CREDIT_SCORE", description="Credit score below target"),
        ]
        return RiskScoreResult(score=55.0, features=features, reason_codes=reason_codes)

    def _get_policy_by_id(ids: List[str]) -> Dict[str, PolicyChunk]:
        chunks = _policy_retriever("", top_k=len(ids))
        return {chunk.chunk_id: chunk for chunk in chunks if chunk.chunk_id in ids}

    def _compose_user_packet(data: Dict[str, object]) -> Dict[str, object]:
        return {"format": "html", "content": "ok"}

    def _request_additional_docs(documents: List[str]) -> Dict[str, object]:
        return {"requested": documents, "request_id": "doc-req-1"}

    class _GovernanceLogger:
        def __init__(self) -> None:
            self.counter = 0

        def __call__(self, event_type: str, payload: Dict[str, object]) -> GovernanceLogRecord:
            self.counter += 1
            return GovernanceLogRecord(event_type=event_type, log_id=f"log-{self.counter}")

    return LoanRiskAssistant(
        policy_docs_retriever=_policy_retriever,
        risk_scoring_api=_risk_scoring_api,
        get_policy_by_id=_get_policy_by_id,
        compose_user_packet=_compose_user_packet,
        request_additional_docs=_request_additional_docs,
        governance_log=_GovernanceLogger(),
    )


def test_assistant_returns_structured_payload(assistant: LoanRiskAssistant) -> None:
    application = LoanApplication(
        application_id="APP-001",
        borrower={"credit_score": 610, "income_verified": False},
        loan={"collateral_required": True},
        region="NY",
        product="smb_term",
    )

    response = assistant.assess(application)

    assert response["risk_score"]["value"] == pytest.approx(55.0)
    assert response["risk_score"]["tier"] == "Med"
    assert response["interest_rate_suggestion"]["band_apr_percent"] == [6.0, 8.5]
    assert "Collateral ownership evidence" in response["requested_documents"]
    assert response["governance_log_ids"]
    assert response["user_packet"]["format"] == "html"
