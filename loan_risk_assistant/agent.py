"""Core orchestration logic for the Loan Risk Assistant."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .models import (
    GovernanceLogRecord,
    InterestBand,
    LoanApplication,
    PolicyChunk,
    RiskFeature,
    RiskScoreResult,
)
from .tools import (
    ComposeUserPacket,
    GetPolicyById,
    GovernanceLog,
    InterestPolicyResolver,
    PolicyDocsRetriever,
    RequestAdditionalDocs,
    RiskScoringAPI,
)


class LoanRiskAssistant:
    """Coordinates the risk assessment workflow across all tools."""

    def __init__(
        self,
        *,
        policy_docs_retriever: PolicyDocsRetriever,
        risk_scoring_api: RiskScoringAPI,
        get_policy_by_id: GetPolicyById,
        compose_user_packet: ComposeUserPacket,
        request_additional_docs: RequestAdditionalDocs,
        governance_log: GovernanceLog,
        interest_policy_resolver: Optional[InterestPolicyResolver] = None,
        policy_top_k: int = 5,
    ) -> None:
        self.policy_docs_retriever = policy_docs_retriever
        self.risk_scoring_api = risk_scoring_api
        self.get_policy_by_id = get_policy_by_id
        self.compose_user_packet = compose_user_packet
        self.request_additional_docs = request_additional_docs
        self.governance_log = governance_log
        self.interest_policy_resolver = interest_policy_resolver
        self.policy_top_k = policy_top_k

    def assess(self, application: LoanApplication) -> Dict[str, Any]:
        """Run the end-to-end assessment for a single application."""

        governance_ids: List[str] = []
        governance_ids.append(
            self._log(
                "problem_received",
                {
                    "application_id": application.application_id,
                    "region": application.region,
                    "product": application.product,
                    "redactions": True,
                },
            ).log_id
        )

        query = self._build_policy_query(application)
        policy_chunks = self.policy_docs_retriever(query, top_k=self.policy_top_k)
        governance_ids.append(
            self._log(
                "retrieval_done",
                {
                    "application_id": application.application_id,
                    "query": query,
                    "chunk_ids": [chunk.chunk_id for chunk in policy_chunks],
                },
            ).log_id
        )

        risk_payload = self._build_risk_payload(application)
        risk_result = self.risk_scoring_api(risk_payload)
        governance_ids.append(
            self._log(
                "risk_scored",
                {
                    "application_id": application.application_id,
                    "risk_score": risk_result.score,
                    "reason_codes": [code.code for code in risk_result.reason_codes],
                },
            ).log_id
        )

        resolved_policies = self._resolve_policy_chunks(policy_chunks)
        policy_citations = self._build_policy_citations(resolved_policies)

        risk_tier = self._tier_from_score(risk_result.score)
        reasons = self._build_reasons(risk_result, resolved_policies)

        requested_documents = self._determine_requested_documents(
            application, risk_result, resolved_policies
        )
        if requested_documents:
            docs_response = self.request_additional_docs(requested_documents)
            tool_response_id: Optional[str] = None
            if isinstance(docs_response, dict):
                for key in ("request_id", "id", "identifier", "response_id", "log_id"):
                    value = docs_response.get(key)
                    if value:
                        tool_response_id = str(value)
                        break

            governance_ids.append(
                self._log(
                    "docs_requested",
                    {
                        "application_id": application.application_id,
                        "requested_documents": requested_documents,
                        "tool_response_id": tool_response_id,
                    },
                ).log_id
            )

        interest_band = self._determine_interest_band(risk_tier, resolved_policies)
        policy_gap = interest_band is None

        user_packet_payload = {
            "application_id": application.application_id,
            "risk_score": {
                "value": risk_result.score,
                "tier": risk_tier,
            },
            "reasons": reasons,
            "requested_documents": requested_documents,
            "policy_citations": policy_citations,
            "interest_band": asdict(interest_band) if interest_band else None,
        }
        user_packet = self.compose_user_packet(user_packet_payload)
        governance_ids.append(
            self._log(
                "packet_composed",
                {
                    "application_id": application.application_id,
                    "payload_keys": list(user_packet_payload.keys()),
                },
            ).log_id
        )

        response: Dict[str, Any] = {
            "application_id": application.application_id,
            "risk_score": {
                "value": risk_result.score,
                "scale": "0-100",
                "tier": risk_tier,
            },
            "reasons": reasons,
            "policy_citations": policy_citations,
            "requested_documents": requested_documents,
            "interest_rate_suggestion": (
                {
                    "band_apr_percent": [
                        round(interest_band.min_apr, 2),
                        round(interest_band.max_apr, 2),
                    ],
                    "basis": interest_band.policy_reference,
                    "conditions": interest_band.conditions,
                }
                if interest_band
                else None
            ),
            "compliance": {
                "region": application.region,
                "product": application.product,
                "policy_gap": policy_gap,
            },
            "governance_log_ids": governance_ids,
            "user_packet": user_packet,
        }

        return response

    # ---------------------------------------------------------------------
    # Helper methods
    # ---------------------------------------------------------------------
    def _log(self, event_type: str, payload: Dict[str, Any]) -> GovernanceLogRecord:
        return self.governance_log(event_type, payload)

    def _build_policy_query(self, application: LoanApplication) -> str:
        context_terms = []
        if application.context:
            for key, value in application.context.items():
                context_terms.append(f"{key}:{value}")
        base_terms = [application.region, application.product, "risk tiering", "interest band", "documentation"]
        return " ".join(term for term in base_terms + context_terms if term)

    def _build_risk_payload(self, application: LoanApplication) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "application_id": application.application_id,
            "borrower": application.borrower,
            "loan": application.loan,
            "region": application.region,
            "product": application.product,
        }
        if application.context:
            payload["context"] = application.context
        return payload

    def _resolve_policy_chunks(self, policy_chunks: List[PolicyChunk]) -> List[PolicyChunk]:
        if not policy_chunks:
            return []
        resolved = self.get_policy_by_id([chunk.chunk_id for chunk in policy_chunks])
        output: List[PolicyChunk] = []
        for chunk in policy_chunks:
            output.append(resolved.get(chunk.chunk_id, chunk))
        return output

    def _build_policy_citations(self, policy_chunks: List[PolicyChunk]) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        for chunk in policy_chunks[:5]:  # limit to reduce noise
            citations.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "title": chunk.title,
                    "section": chunk.section,
                    "quote": chunk.quote(),
                }
            )
        return citations

    def _tier_from_score(self, score: float) -> str:
        if score < 34:
            return "Low"
        if score < 67:
            return "Med"
        return "High"

    def _build_reasons(self, risk_result: RiskScoreResult, policy_chunks: List[PolicyChunk]) -> List[Dict[str, Any]]:
        reasons: List[Dict[str, Any]] = []

        feature_lookup: Dict[str, RiskFeature] = {feature.code: feature for feature in risk_result.features}
        for reason in risk_result.reason_codes:
            feature = feature_lookup.get(reason.code)
            detail = reason.description
            if feature:
                direction = "raised" if feature.direction.lower() == "increase" else "reduced"
                detail = (
                    f"{reason.description} — feature value {feature.value!r} {direction} risk"
                )
            reasons.append(
                {
                    "label": reason.description,
                    "detail": detail,
                    "source": {"type": "feature", "id_or_code": reason.code},
                }
            )

        for chunk in policy_chunks:
            if "guidance" in chunk.metadata:
                reasons.append(
                    {
                        "label": chunk.metadata.get("guidance", "Policy guidance"),
                        "detail": chunk.quote(),
                        "source": {"type": "policy", "id_or_code": chunk.chunk_id},
                    }
                )
        return reasons[:8]

    def _determine_requested_documents(
        self,
        application: LoanApplication,
        risk_result: RiskScoreResult,
        policy_chunks: List[PolicyChunk],
    ) -> List[str]:
        documents = set()

        borrower = application.borrower
        employment_type = borrower.get("employment_type")
        if employment_type == "self_employed":
            documents.add("Most recent 2 years of tax returns")
        if not borrower.get("income_verified", False):
            documents.add("Recent income verification (e.g., pay stubs or bank statements)")

        if application.loan.get("collateral_required") and not application.loan.get("collateral_documents"):
            documents.add("Collateral ownership evidence")

        for code in risk_result.reason_codes:
            if code.code.upper().startswith("DTI"):
                documents.add("Detailed debt obligation schedule")
            if code.code.upper().startswith("CREDIT"):
                documents.add("Updated credit bureau report")

        for chunk in policy_chunks:
            for document in chunk.metadata.get("required_documents", []):
                documents.add(document)

        return sorted(documents)

    def _determine_interest_band(
        self, risk_tier: str, policy_chunks: List[PolicyChunk]
    ) -> Optional[InterestBand]:
        if self.interest_policy_resolver:
            band = self.interest_policy_resolver(policy_chunks, risk_tier)
            if band:
                return band

        for chunk in policy_chunks:
            band_data = chunk.metadata.get("interest_band")
            if not band_data:
                continue
            min_apr = band_data.get("min_apr")
            max_apr = band_data.get("max_apr")
            if min_apr is None or max_apr is None:
                continue
            reference = band_data.get("policy_reference", chunk.chunk_id)
            conditions = band_data.get("conditions", [])
            return InterestBand(min_apr=min_apr, max_apr=max_apr, policy_reference=reference, conditions=conditions)
        return None
