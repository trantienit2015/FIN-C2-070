"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.
#
# Every agent-specific field is wrapped in NotRequired[...]: absent
# fields must not break msgpack checkpoint resume, and nodes read them via
# state.get(..., default) rather than state[...].

from typing import NotRequired

from framework.schemas.agent_state import AgentState


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to Any
# and reports every NotRequired below as valid-type. The fields are correct (the state
# contract requires NotRequired) -- the report is a packaging artifact, suppressed per field.
# Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """Agent state for FIN-C2-070 Advisory Call Compliance & Suitability Check.

    Raw audio bytes are never stored here — only the temp file path.
    """

    audio_path: NotRequired[str]  # type: ignore[valid-type]
    jurisdiction_profile: NotRequired[str]  # type: ignore[valid-type]
    diarized_transcript: NotRequired[list[dict]]  # type: ignore[valid-type]
    utterance_classifications: NotRequired[list[dict]]  # type: ignore[valid-type]
    compliance_findings: NotRequired[list[dict]]  # type: ignore[valid-type]
    verdict_report: NotRequired[dict]  # type: ignore[valid-type]
