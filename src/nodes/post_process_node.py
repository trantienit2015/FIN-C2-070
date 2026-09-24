"""AgentCore Platform v1.0"""

# Outer post_process — GenerateVerdict (§4 step 5 of the proposed workflow).
# Composes the per-dimension compliance verdict report with evidence timestamps,
# attaches the mandatory non-advice disclaimer (re-checked as non-suppressible by
# the S-3 hook below), and cleans up the temp audio file on every exit path.

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.audio_validation_service import cleanup_temp_audio

_NON_ADVICE_DISCLAIMER = (
    "本レポートは金商法37条の3 適合性原則等の観点から通話内容を機械的に照合した"
    "参考情報であり、法的助言ではありません。最終判断は必ずコンプライアンス"
    "担当者が行ってください。 / This report is a mechanical suitability-audit "
    "reference and does not constitute legal or investment advice; a compliance "
    "officer must make the final determination."
)


class PostProcessNode(FunctionNode):
    """GenerateVerdict: assemble verdict report + mandatory disclaimer + cleanup."""

    # S-1: outer node — matches config/agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Cleanup runs on every exit path (success or upstream error) so the
        # submitted call recording is never left on disk after the audit.
        cleanup_temp_audio(state.get("audio_path"))

        if state.get("status") == AgentStatus.ERROR.value:
            # An upstream node already rejected the request — pass the error
            # through without fabricating a verdict.
            emit_trace_event(
                "compliance_verdict_skipped",
                {"correlation_id": state.get("correlation_id"), "reason": "upstream_error"},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        findings = state.get("compliance_findings", [])
        dimensions: dict[str, dict[str, Any]] = {}
        for f in findings:
            dimensions[f.get("dimension", "unknown")] = {
                "verdict": f.get("verdict", "needs_review"),
                "evidence_timestamps": f.get("evidence_timestamps", []),
            }

        verdicts = [d["verdict"] for d in dimensions.values()]
        if "violation" in verdicts:
            overall_verdict = "violation"
        elif "needs_review" in verdicts:
            overall_verdict = "needs_review"
        else:
            overall_verdict = "compliant"

        verdict_report = {
            "dimensions": dimensions,
            "overall_verdict": overall_verdict,
            "disclaimer": _NON_ADVICE_DISCLAIMER,
        }

        emit_trace_event(
            "compliance_verdict_generated",
            {"correlation_id": state.get("correlation_id"), "overall_verdict": overall_verdict},
            state,
        )

        return {
            "verdict_report": verdict_report,
            "formatted_output": verdict_report,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation-variant hook: the non-advice disclaimer MUST always
        be present in this node's own output — non-suppressible re-check."""
        report = state.get("verdict_report")
        if isinstance(report, dict) and report and not report.get("disclaimer"):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["GenerateVerdict S-3: mandatory non-advice disclaimer missing from verdict_report"],
            }
        return state
