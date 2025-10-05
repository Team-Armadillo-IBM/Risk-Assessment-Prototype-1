"""Example execution of the LoanRiskAssistant with stubbed tools."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loan_risk_assistant import (
    GovernanceLogRecord,
    InterestBand,
    LoanApplication,
    LoanRiskAssistant,
    PolicyChunk,
    ReasonCode,
    RiskFeature,
    RiskScoreResult,
)


def _policy_retriever(query: str, top_k: int = 5) -> List[PolicyChunk]:
    metadata = {
        "guidance": "Tier-based interest premium",
        "interest_band": {
            "min_apr": 7.25,
            "max_apr": 9.5,
            "policy_reference": "POL-INT-2024-1",
            "conditions": ["Auto-pay enrollment"],
        },
        "required_documents": [
            "Signed personal financial statement",
        ],
    }
    return [
        PolicyChunk(
            chunk_id="chunk-001",
            title="SMB Term Lending Manual",
            section="4.2",
            text="For high-risk SMB borrowers, apply a premium between 7.25% and 9.5% APR contingent on auto-pay enrollment.",
            metadata=metadata,
        )
    ]


def _risk_scoring_api(payload: Dict[str, object]) -> RiskScoreResult:
    features = [
        RiskFeature(
            code="CREDIT_SCORE",
            description="Credit score below 680",
            value=payload["borrower"].get("credit_score", 0),
            direction="increase",
            weight=0.27,
        ),
        RiskFeature(
            code="DTI_RATIO",
            description="Debt-to-income ratio above 40%",
            value=payload["borrower"].get("dti", 0.0),
            direction="increase",
            weight=0.19,
        ),
    ]
    reason_codes = [
        ReasonCode(code="CREDIT_SCORE", description="Credit score below tier threshold"),
        ReasonCode(code="DTI_RATIO", description="Elevated debt-to-income ratio"),
    ]
    return RiskScoreResult(score=72.0, features=features, reason_codes=reason_codes)


def _get_policy_by_id(ids: List[str]) -> Dict[str, PolicyChunk]:
    chunks = _policy_retriever("", top_k=len(ids))
    return {chunk.chunk_id: chunk for chunk in chunks if chunk.chunk_id in ids}


def _compose_user_packet(data: Dict[str, object]) -> Dict[str, object]:
    html = "<h1>Loan Assessment</h1>"
    html += f"<p>Risk Score: {data['risk_score']['value']} ({data['risk_score']['tier']})</p>"
    html += "<ul>" + "".join(
        f"<li>{reason['label']}: {reason['detail']}</li>" for reason in data["reasons"]
    ) + "</ul>"
    return {"format": "html", "content": html}


def _request_additional_docs(documents: List[str]) -> Dict[str, object]:
    return {"requested": documents, "request_id": "doc-req-1"}


class _GovernanceLogger:
    def __init__(self) -> None:
        self._counter = 0

    def __call__(self, event_type: str, payload: Dict[str, object]) -> GovernanceLogRecord:
        self._counter += 1
        return GovernanceLogRecord(event_type=event_type, log_id=f"log-{self._counter}")


def main() -> None:
    assistant = LoanRiskAssistant(
        policy_docs_retriever=_policy_retriever,
        risk_scoring_api=_risk_scoring_api,
        get_policy_by_id=_get_policy_by_id,
        compose_user_packet=_compose_user_packet,
        request_additional_docs=_request_additional_docs,
        governance_log=_GovernanceLogger(),
    )

    application = LoanApplication(
        application_id="APP-123",
        borrower={
            "credit_score": 645,
            "dti": 0.46,
            "employment_type": "self_employed",
            "income_verified": False,
        },
        loan={
            "amount": 250000,
            "term_months": 60,
            "collateral_required": True,
        },
        region="CA",
        product="smb_term",
    )

    response = assistant.assess(application)
    print(response)


if __name__ == "__main__":
    main()
