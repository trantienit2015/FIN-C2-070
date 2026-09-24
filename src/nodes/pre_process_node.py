"""AgentCore Platform v1.0"""

# Outer pre_process — ValidateInput (§4 step 1 of the proposed workflow).
# Deterministic (rule/pattern, non-LLM) audio-format check + S-2 deterministic
# PII scan on the non-audio payload fields. Sets validated_input (JSON string)
# consumed by the inner subgraph via AdvisoryCallWorkflowGraphNode.extract_input().

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.audio_validation_service import is_valid_audio_format
from src.services.pii_scanner_service import contains_regulated_pii

_DEFAULT_JURISDICTION_PROFILE = "jp_fiea_37_3"
# Optional pre-transcribed input (see README "Pre-transcribed input"): bounded so an
# oversized caller payload is rejected here rather than walked by every inner node.
_MAX_TRANSCRIPT_UTTERANCES = 500
_MAX_UTTERANCE_TEXT_CHARS = 2000


def _validate_transcript(transcript: Any) -> str | None:
    """Return an error message for a malformed optional transcript, else None."""
    if not isinstance(transcript, list) or not transcript:
        return "transcript must be a non-empty list of utterances"
    if len(transcript) > _MAX_TRANSCRIPT_UTTERANCES:
        return f"transcript exceeds {_MAX_TRANSCRIPT_UTTERANCES} utterances"
    for u in transcript:
        if not isinstance(u, dict) or not isinstance(u.get("text"), str):
            return "each transcript utterance must be an object with a string text"
        if len(u["text"]) > _MAX_UTTERANCE_TEXT_CHARS:
            return f"transcript utterance text exceeds {_MAX_UTTERANCE_TEXT_CHARS} characters"
        for key in ("start_ts", "end_ts"):
            if key in u and (isinstance(u[key], bool) or not isinstance(u[key], (int, float))):
                return f"transcript utterance {key} must be a number"
    return None


class PreProcessNode(FunctionNode):
    """ValidateInput: deterministic audio-format gate + S-2 PII auto-reject."""

    # S-1: outer node — trust level matches config/agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
            if not isinstance(payload, dict):
                payload = {}
        except (ValueError, TypeError):
            payload = {}

        audio_path = payload.get("audio_path") or state.get("audio_path", "")
        jurisdiction_profile = (
            payload.get("jurisdiction_profile") or state.get("jurisdiction_profile") or _DEFAULT_JURISDICTION_PROFILE
        )

        emit_trace_event(
            "advisory_call_input_received",
            {"correlation_id": state.get("correlation_id"), "has_audio_path": bool(audio_path)},
            state,
        )

        if not is_valid_audio_format(audio_path):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ValidateInput: audio_path missing or not MP3/WAV format"],
            }

        if contains_regulated_pii(jurisdiction_profile):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ValidateInput: regulated PII (APPI) detected outside audio payload"],
            }

        validated: dict[str, Any] = {"audio_path": audio_path, "jurisdiction_profile": jurisdiction_profile}
        transcript = payload.get("transcript")
        if transcript is not None:
            transcript_error = _validate_transcript(transcript)
            if transcript_error:
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"ValidateInput: {transcript_error}"],
                }
            validated["transcript"] = [
                {
                    "speaker": str(u.get("speaker", "unknown")),
                    "text": u["text"],
                    "start_ts": u.get("start_ts", 0.0),
                    "end_ts": u.get("end_ts", 0.0),
                }
                for u in transcript
            ]

        validated_input = json.dumps(validated, ensure_ascii=False)
        return {
            "audio_path": audio_path,
            "jurisdiction_profile": jurisdiction_profile,
            "validated_input": validated_input,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain check: deterministic regulated-PII scan on raw user_input.

        Never raises — returns the (possibly unchanged) state dict, or an
        ERROR-status dict when regulated PII is found outside the audio payload.
        """
        raw = state.get("user_input", "")
        if isinstance(raw, str) and contains_regulated_pii(raw):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["S-2: regulated PII (APPI 個人情報 / 個人番号) detected in raw input"],
            }
        return state
