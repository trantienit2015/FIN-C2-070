"""AgentCore Platform v1.0"""

# Inner subgraph node — ClassifyUtterances (§4 step 3). LLM classifies each
# utterance into one of four categories (intent/context judgment, not
# rule-expressible). Trust: inner node, authenticated once at outer backbone.

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_CATEGORIES = ("product_recommendation", "risk_disclosure", "customer_objection", "suitability_inquiry")

# Deterministic keyword fallback, used ONLY when no language model is configured
# (e.g. the standalone deploy path without an LLM key). It is a coarse, bounded
# baseline, not a substitute for the LLM intent judgment, and every result it
# produces is labelled method="keyword_fallback" so downstream consumers can tell.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("risk_disclosure", ("リスク", "元本割れ", "損失", "価格変動", "risk", "loss")),
    ("suitability_inquiry", ("投資経験", "投資目的", "資産状況", "プロファイル", "意向", "experience", "objective")),
    ("customer_objection", ("不安", "心配", "結構です", "concern", "not interested")),
)


def _keyword_classify(text: str) -> str:
    lowered = text.lower()
    for category, keywords in _KEYWORD_RULES:
        if any(k.lower() in lowered for k in keywords):
            return category
    return "product_recommendation"


def _llm_classify(llm: Any, text: str) -> str:
    """Classify via an injected client: a `classify(text, categories)` method when the
    client provides one, otherwise the BaseLLM `complete(messages)` contract."""
    if hasattr(llm, "classify"):
        return str(llm.classify(text, _CATEGORIES))
    prompt = (
        "Classify the following financial-advisory call utterance into exactly one of: "
        + ", ".join(_CATEGORIES)
        + ". Reply with the category name only.\n\nUtterance: "
        + text
    )
    response = llm.complete([{"role": "user", "content": prompt}])
    content = response.get("content", "") if isinstance(response, dict) else ""
    for category in _CATEGORIES:
        if category in str(content):
            return category
    return ""


class ClassifyUtterancesNode(FunctionNode):
    """LLM utterance classification into the four compliance-relevant categories."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        diarized_transcript = state.get("diarized_transcript", [])
        if not diarized_transcript:
            emit_trace_event(
                "utterance_classification_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "empty_diarized_transcript"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ClassifyUtterances: diarized_transcript is empty"],
            }

        method = "llm" if self._llm is not None else "keyword_fallback"
        classifications = []
        for utterance in diarized_transcript:
            text = utterance.get("text", "")
            if self._llm is not None:
                category = _llm_classify(self._llm, text)
            else:
                category = _keyword_classify(text)
            if category not in _CATEGORIES:
                category = "product_recommendation"
            classifications.append({**utterance, "category": category, "method": method})

        emit_trace_event(
            "utterances_classified",
            {
                "correlation_id": state.get("correlation_id"),
                "utterance_count": len(classifications),
                "method": method,
            },
            state,
        )

        return {"utterance_classifications": classifications, "status": AgentStatus.SUCCESS.value}
