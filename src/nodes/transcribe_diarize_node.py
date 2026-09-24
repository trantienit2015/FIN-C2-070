"""AgentCore Platform v1.0"""

# Inner subgraph node — TranscribeDiarize (§4 step 2). Runs INSIDE the Cat 2
# inner BaseGraph (src/graph/domain_workflow_graph.py). Trust is authenticated
# once at the outer backbone, so inner nodes declare ANONYMOUS (never escalate).

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.pii_scanner_service import mask_regulated_pii


class TranscribeDiarizeNode(FunctionNode):
    """Audio -> timestamped, speaker-diarized transcript with APPI masking."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, transcription_service: Any = None) -> None:
        self._transcription_service = transcription_service

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except (ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        audio_path = payload.get("audio_path", "")
        supplied_transcript = payload.get("transcript")

        if self._transcription_service is not None:
            transcript_source = "transcription_service"
            raw_utterances = self._transcription_service.transcribe(audio_path)
        elif isinstance(supplied_transcript, list):
            # Explicit no-transcriber path: the caller supplied an already-transcribed,
            # diarized transcript (validated and bounded by ValidateInput). No speech-to-text
            # happens here; the same PII masking below still applies.
            transcript_source = "caller_supplied_transcript"
            raw_utterances = [u for u in supplied_transcript if isinstance(u, dict)]
        else:
            emit_trace_event(
                "call_transcription_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "transcription_service_not_configured"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["TranscribeDiarize: transcription_service not configured and no transcript supplied"],
            }

        if not raw_utterances:
            emit_trace_event(
                "call_transcription_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "no_utterances_returned"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["TranscribeDiarize: transcription returned no utterances"],
            }

        diarized_transcript = [
            {
                "speaker": u.get("speaker", "unknown"),
                "text": mask_regulated_pii(u.get("text", "")),
                "start_ts": u.get("start_ts", 0.0),
                "end_ts": u.get("end_ts", 0.0),
            }
            for u in raw_utterances
        ]

        emit_trace_event(
            "call_transcribed_diarized",
            {
                "correlation_id": state.get("correlation_id"),
                "utterance_count": len(diarized_transcript),
                "transcript_source": transcript_source,
            },
            state,
        )

        return {"diarized_transcript": diarized_transcript, "status": AgentStatus.SUCCESS.value}
