"""Data models supporting the loan risk assistant orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PolicyChunk:
    """Represents a retrieved policy chunk."""

    chunk_id: str
    title: str
    section: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def quote(self, word_limit: int = 50) -> str:
        """Return a truncated quote respecting the <=50 words requirement."""
        words = self.text.split()
        if len(words) <= word_limit:
            return self.text
        return " ".join(words[:word_limit])


@dataclass
class RiskFeature:
    """Feature contribution returned by the risk scoring API."""

    code: str
    description: str
    value: Any
    direction: str  # e.g. "increase" or "decrease"
    weight: float


@dataclass
class ReasonCode:
    """Structured reason code returned by the risk scoring API."""

    code: str
    description: str


@dataclass
class RiskScoreResult:
    """Standardised output from the risk scoring API."""

    score: float
    features: List[RiskFeature]
    reason_codes: List[ReasonCode]


@dataclass
class LoanApplication:
    """Minimal loan application payload passed to the assistant."""

    application_id: str
    borrower: Dict[str, Any]
    loan: Dict[str, Any]
    region: str
    product: str
    context: Optional[Dict[str, Any]] = None


@dataclass
class GovernanceLogRecord:
    """Governance log response wrapper."""

    event_type: str
    log_id: str
    payload_hash: Optional[str] = None


@dataclass
class InterestBand:
    """Represents a policy backed interest band suggestion."""

    min_apr: float
    max_apr: float
    policy_reference: str
    conditions: List[str] = field(default_factory=list)
