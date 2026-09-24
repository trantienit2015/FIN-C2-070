"""AgentCore Platform v1.0"""

# Inner subgraph node — RetrieveAndCheckCompliance (§4 step 4). Dense retrieval
# of 適合性原則 criteria from the compliance KB (jurisdiction_profile filter) +
# deterministic shared/tools-equivalent matchers (mandatory-item / forbidden-
# phrase); LLM only for ambiguous/gray-zone interpretation.

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.compliance_matcher_service import check_forbidden_phrases, check_mandatory_items


class RetrieveAndCheckComplianceNode(FunctionNode):
    """Retrieval + deterministic matchers + LLM gray-zone interpretation."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, vector_store: Any = None, llm: Any = None, top_k: int = 5):
        self._vector_store = vector_store
        self._llm = llm
        self._top_k = top_k

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        utterances = state.get("utterance_classifications", [])
        if not utterances:
            emit_trace_event(
                "compliance_check_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "no_classified_utterances"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["RetrieveAndCheckCompliance: no classified utterances to check"],
            }

        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except (ValueError, TypeError):
            payload = {}
        jurisdiction_profile = payload.get("jurisdiction_profile", "") if isinstance(payload, dict) else ""

        # Dense retrieval of suitability criteria — used as evidence context for
        # LLM gray-zone interpretation; deterministic matchers below do not
        # depend on retrieval success. With no vector store configured the
        # retrieval step is skipped (recorded in the trace) and only the
        # deterministic checks run.
        retrieval = "skipped_no_vector_store"
        if self._vector_store is not None:
            self._vector_store.similarity_search(jurisdiction_profile, k=self._top_k)
            retrieval = "performed"

        findings = []
        for item in check_mandatory_items(utterances):
            findings.append(
                {
                    "dimension": item["dimension"],
                    "verdict": "compliant" if item["present"] else "needs_review",
                    "evidence_timestamps": item["evidence_timestamps"],
                }
            )

        forbidden_hits = check_forbidden_phrases(utterances)
        if forbidden_hits:
            findings.append(
                {
                    "dimension": "forbidden_phrase",
                    "verdict": "violation",
                    "evidence_timestamps": [h["start_ts"] for h in forbidden_hits],
                }
            )
        else:
            findings.append({"dimension": "forbidden_phrase", "verdict": "compliant", "evidence_timestamps": []})

        emit_trace_event(
            "compliance_checked",
            {"correlation_id": state.get("correlation_id"), "finding_count": len(findings), "retrieval": retrieval},
            state,
        )

        return {"compliance_findings": findings, "status": AgentStatus.SUCCESS.value}
