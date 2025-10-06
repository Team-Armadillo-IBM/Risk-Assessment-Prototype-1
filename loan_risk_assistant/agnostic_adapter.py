"""Adapters for integrating :mod:`loan_risk_assistant` with the agnostic framework."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .agent import LoanRiskAssistant
from .models import (
    GovernanceLogRecord,
    InterestBand,
    LoanApplication,
    PolicyChunk,
    ReasonCode,
    RiskFeature,
    RiskScoreResult,
)


class AgnosticToolAdapter:
    """Wrap a domain callable in the agnostic framework's dict-based protocol."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self._handler = handler

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._handler(payload)


def _policy_chunk_from_dict(data: Dict[str, Any]) -> PolicyChunk:
    return PolicyChunk(
        chunk_id=data["chunk_id"],
        title=data["title"],
        section=data["section"],
        text=data["text"],
        metadata=data.get("metadata", {}),
    )


def _policy_chunk_to_dict(chunk: PolicyChunk) -> Dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "title": chunk.title,
        "section": chunk.section,
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


def _risk_feature_from_dict(data: Dict[str, Any]) -> RiskFeature:
    return RiskFeature(
        code=data["code"],
        description=data["description"],
        value=data.get("value"),
        direction=data["direction"],
        weight=float(data["weight"]),
    )


def _risk_feature_to_dict(feature: RiskFeature) -> Dict[str, Any]:
    return {
        "code": feature.code,
        "description": feature.description,
        "value": feature.value,
        "direction": feature.direction,
        "weight": feature.weight,
    }


def _reason_code_from_dict(data: Dict[str, Any]) -> ReasonCode:
    return ReasonCode(code=data["code"], description=data["description"])


def _reason_code_to_dict(code: ReasonCode) -> Dict[str, Any]:
    return {"code": code.code, "description": code.description}


def _risk_result_from_dict(data: Dict[str, Any]) -> RiskScoreResult:
    features = [_risk_feature_from_dict(item) for item in data.get("features", [])]
    reason_codes = [_reason_code_from_dict(item) for item in data.get("reason_codes", [])]
    return RiskScoreResult(score=float(data["score"]), features=features, reason_codes=reason_codes)


def _risk_result_to_dict(result: RiskScoreResult) -> Dict[str, Any]:
    return {
        "score": result.score,
        "features": [_risk_feature_to_dict(feature) for feature in result.features],
        "reason_codes": [_reason_code_to_dict(code) for code in result.reason_codes],
    }


def _governance_record_from_dict(data: Dict[str, Any]) -> GovernanceLogRecord:
    return GovernanceLogRecord(
        event_type=data["event_type"],
        log_id=data["log_id"],
        payload_hash=data.get("payload_hash"),
    )


def _governance_record_to_dict(record: GovernanceLogRecord) -> Dict[str, Any]:
    result = {"event_type": record.event_type, "log_id": record.log_id}
    if record.payload_hash is not None:
        result["payload_hash"] = record.payload_hash
    return result


def _interest_band_from_dict(data: Dict[str, Any]) -> InterestBand:
    return InterestBand(
        min_apr=float(data["min_apr"]),
        max_apr=float(data["max_apr"]),
        policy_reference=data["policy_reference"],
        conditions=list(data.get("conditions", [])),
    )


def _interest_band_to_dict(band: InterestBand) -> Dict[str, Any]:
    return {
        "min_apr": band.min_apr,
        "max_apr": band.max_apr,
        "policy_reference": band.policy_reference,
        "conditions": band.conditions,
    }


def adapt_policy_docs_retriever(tool: Callable[[str, int], List[PolicyChunk]]) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload.get("query", "")
        top_k = int(payload.get("top_k", 5))
        chunks = tool(query, top_k=top_k)
        return {"chunks": [_policy_chunk_to_dict(chunk) for chunk in chunks]}

    return AgnosticToolAdapter(
        name="policy_docs_retriever",
        description="Retrieve policy chunks relevant to a loan application query.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
        handler=handler,
    )


def adapt_risk_scoring_api(tool: Callable[[Dict[str, Any]], RiskScoreResult]) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        risk_result = tool(payload["payload"])
        return _risk_result_to_dict(risk_result)

    return AgnosticToolAdapter(
        name="risk_scoring_api",
        description="Call the bank's risk scoring service.",
        input_schema={"type": "object", "properties": {"payload": {"type": "object"}}},
        output_schema={"type": "object", "properties": {"score": {"type": "number"}}},
        handler=handler,
    )


def adapt_get_policy_by_id(tool: Callable[[Iterable[str]], Dict[str, PolicyChunk]]) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        ids = payload.get("ids", [])
        resolved = tool(ids)
        return {"chunks": [_policy_chunk_to_dict(chunk) for chunk in resolved.values()]}

    return AgnosticToolAdapter(
        name="get_policy_by_id",
        description="Resolve canonical policy chunks by identifier.",
        input_schema={"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}}},
        output_schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
        handler=handler,
    )


def adapt_compose_user_packet(tool: Callable[[Dict[str, Any]], Dict[str, Any]]) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"packet": tool(payload["data"])}

    return AgnosticToolAdapter(
        name="compose_user_packet",
        description="Compose a channel specific packet from the assessment payload.",
        input_schema={"type": "object", "properties": {"data": {"type": "object"}}},
        output_schema={"type": "object", "properties": {"packet": {"type": "object"}}},
        handler=handler,
    )


def adapt_request_additional_docs(tool: Callable[[List[str]], Dict[str, Any]]) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        documents = list(payload.get("documents", []))
        return {"request": tool(documents)}

    return AgnosticToolAdapter(
        name="request_additional_docs",
        description="Trigger the document collection workflow.",
        input_schema={"type": "object", "properties": {"documents": {"type": "array", "items": {"type": "string"}}}},
        output_schema={"type": "object", "properties": {"request": {"type": "object"}}},
        handler=handler,
    )


def adapt_governance_log(tool: Callable[[str, Dict[str, Any]], GovernanceLogRecord]) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        record = tool(payload["event_type"], payload.get("payload", {}))
        return _governance_record_to_dict(record)

    return AgnosticToolAdapter(
        name="governance_log",
        description="Write an event to the governance log.",
        input_schema={
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "payload": {"type": "object"},
            },
        },
        output_schema={"type": "object", "properties": {"log_id": {"type": "string"}}},
        handler=handler,
    )


def adapt_interest_policy_resolver(
    tool: Callable[[List[PolicyChunk], str], Optional[InterestBand]]
) -> AgnosticToolAdapter:
    def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        chunks = [_policy_chunk_from_dict(item) for item in payload.get("policy_chunks", [])]
        band = tool(chunks, payload["risk_tier"])
        return {"band": _interest_band_to_dict(band) if band else None}

    return AgnosticToolAdapter(
        name="interest_policy_resolver",
        description="Derive an interest band from the resolved policies.",
        input_schema={
            "type": "object",
            "properties": {
                "policy_chunks": {"type": "array"},
                "risk_tier": {"type": "string"},
            },
        },
        output_schema={"type": "object", "properties": {"band": {"type": ["object", "null"]}}},
        handler=handler,
    )


def loan_application_from_dict(payload: Dict[str, Any]) -> LoanApplication:
    return LoanApplication(
        application_id=payload["application_id"],
        borrower=dict(payload["borrower"]),
        loan=dict(payload["loan"]),
        region=payload["region"],
        product=payload["product"],
        context=payload.get("context"),
    )


class LoanRiskAgnosticAgent:
    """Adapter that allows the assistant to run inside the agnostic runtime."""

    def __init__(
        self,
        invoke_tool: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        *,
        available_tools: Optional[Iterable[str]] = None,
        policy_top_k: int = 5,
    ) -> None:
        self._invoke_tool = invoke_tool
        tool_set = set(available_tools or [])

        interest_resolver = None
        if "interest_policy_resolver" in tool_set:
            interest_resolver = self._wrap_interest_policy_resolver()

        self._assistant = LoanRiskAssistant(
            policy_docs_retriever=self._wrap_policy_docs_retriever(),
            risk_scoring_api=self._wrap_risk_scoring_api(),
            get_policy_by_id=self._wrap_get_policy_by_id(),
            compose_user_packet=self._wrap_compose_user_packet(),
            request_additional_docs=self._wrap_request_additional_docs(),
            governance_log=self._wrap_governance_log(),
            interest_policy_resolver=interest_resolver,
            policy_top_k=policy_top_k,
        )

    # ------------------------------------------------------------------
    # Wrappers exposed to the assistant
    # ------------------------------------------------------------------
    def _wrap_policy_docs_retriever(self) -> Callable[[str, int], List[PolicyChunk]]:
        def _call(query: str, top_k: int = 5) -> List[PolicyChunk]:
            result = self._invoke_tool(
                "policy_docs_retriever", {"query": query, "top_k": top_k}
            )
            return [
                _policy_chunk_from_dict(item)
                for item in result.get("chunks", [])
            ]

        return _call

    def _wrap_risk_scoring_api(self) -> Callable[[Dict[str, Any]], RiskScoreResult]:
        def _call(payload: Dict[str, Any]) -> RiskScoreResult:
            result = self._invoke_tool("risk_scoring_api", {"payload": payload})
            return _risk_result_from_dict(result)

        return _call

    def _wrap_get_policy_by_id(self) -> Callable[[Iterable[str]], Dict[str, PolicyChunk]]:
        def _call(ids: Iterable[str]) -> Dict[str, PolicyChunk]:
            result = self._invoke_tool("get_policy_by_id", {"ids": list(ids)})
            chunks = {
                item["chunk_id"]: _policy_chunk_from_dict(item)
                for item in result.get("chunks", [])
            }
            return chunks

        return _call

    def _wrap_compose_user_packet(self) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        def _call(data: Dict[str, Any]) -> Dict[str, Any]:
            result = self._invoke_tool("compose_user_packet", {"data": data})
            return result.get("packet", {})

        return _call

    def _wrap_request_additional_docs(self) -> Callable[[List[str]], Dict[str, Any]]:
        def _call(documents: List[str]) -> Dict[str, Any]:
            result = self._invoke_tool(
                "request_additional_docs", {"documents": list(documents)}
            )
            return result.get("request", {})

        return _call

    def _wrap_governance_log(self) -> Callable[[str, Dict[str, Any]], GovernanceLogRecord]:
        def _call(event_type: str, payload: Dict[str, Any]) -> GovernanceLogRecord:
            result = self._invoke_tool(
                "governance_log", {"event_type": event_type, "payload": payload}
            )
            return _governance_record_from_dict(result)

        return _call

    def _wrap_interest_policy_resolver(self) -> Callable[[List[PolicyChunk], str], Optional[InterestBand]]:
        def _call(policy_chunks: List[PolicyChunk], risk_tier: str) -> Optional[InterestBand]:
            result = self._invoke_tool(
                "interest_policy_resolver",
                {
                    "policy_chunks": [
                        _policy_chunk_to_dict(chunk) for chunk in policy_chunks
                    ],
                    "risk_tier": risk_tier,
                },
            )
            band_payload = result.get("band")
            if not band_payload:
                return None
            return _interest_band_from_dict(band_payload)

        return _call

    # ------------------------------------------------------------------
    # Runtime entry point
    # ------------------------------------------------------------------
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        application = loan_application_from_dict(payload)
        response = self._assistant.assess(application)
        return asdict(application) | response  # enrich context for frameworks


def available_tool_adapters(
    *,
    policy_docs_retriever: Callable[[str, int], List[PolicyChunk]],
    risk_scoring_api: Callable[[Dict[str, Any]], RiskScoreResult],
    get_policy_by_id: Callable[[Iterable[str]], Dict[str, PolicyChunk]],
    compose_user_packet: Callable[[Dict[str, Any]], Dict[str, Any]],
    request_additional_docs: Callable[[List[str]], Dict[str, Any]],
    governance_log: Callable[[str, Dict[str, Any]], GovernanceLogRecord],
    interest_policy_resolver: Optional[
        Callable[[List[PolicyChunk], str], Optional[InterestBand]]
    ] = None,
) -> Sequence[AgnosticToolAdapter]:
    """Expose the assistant's required tools in the agnostic format."""

    adapters: List[AgnosticToolAdapter] = [
        adapt_policy_docs_retriever(policy_docs_retriever),
        adapt_risk_scoring_api(risk_scoring_api),
        adapt_get_policy_by_id(get_policy_by_id),
        adapt_compose_user_packet(compose_user_packet),
        adapt_request_additional_docs(request_additional_docs),
        adapt_governance_log(governance_log),
    ]
    if interest_policy_resolver is not None:
        adapters.append(adapt_interest_policy_resolver(interest_policy_resolver))
    return adapters
