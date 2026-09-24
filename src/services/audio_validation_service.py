"""AgentCore Platform v1.0"""

# Deterministic (non-LLM) helpers: audio format validation + temp file cleanup.
# Pure functions — no state, no security gates. Called by ValidateInputNode
# (pre_process) and GenerateVerdictNode (post_process).

from __future__ import annotations

import os

_ALLOWED_EXTENSIONS = (".mp3", ".wav")


def is_valid_audio_format(audio_path: str) -> bool:
    """Deterministic rule/pattern check — no LLM involved."""
    if not audio_path or not isinstance(audio_path, str):
        return False
    return audio_path.lower().endswith(_ALLOWED_EXTENSIONS)


def cleanup_temp_audio(audio_path: str | None) -> bool:
    """Delete the temp audio file if present. Safe no-op when missing.

    Called on both the success and error exit paths so a submitted call
    recording is never left on disk after the audit completes.
    """
    if not audio_path:
        return False
    try:
        if os.path.exists(audio_path):
            os.remove(audio_path)
            return True
    except OSError:
        return False
    return False
