"""Protocol definitions for the external tools used by the assistant."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol

from .models import GovernanceLogRecord, InterestBand, PolicyChunk, RiskScoreResult


class PolicyDocsRetriever(Protocol):
    def __call__(self, query: str, top_k: int = 5) -> List[PolicyChunk]:
        ...


class RiskScoringAPI(Protocol):
    def __call__(self, payload: Dict[str, Any]) -> RiskScoreResult:
        ...


class GetPolicyById(Protocol):
    def __call__(self, ids: Iterable[str]) -> Dict[str, PolicyChunk]:
        ...


class ComposeUserPacket(Protocol):
    def __call__(self, data: Dict[str, Any]) -> Dict[str, Any]:
        ...


class RequestAdditionalDocs(Protocol):
    def __call__(self, documents: List[str]) -> Dict[str, Any]:
        ...


class GovernanceLog(Protocol):
    def __call__(self, event_type: str, payload: Dict[str, Any]) -> GovernanceLogRecord:
        ...


class InterestPolicyResolver(Protocol):
    """Optional helper that computes interest bands from policy metadata."""

    def __call__(self, policy_chunks: List[PolicyChunk], risk_tier: str) -> InterestBand | None:
        ...
