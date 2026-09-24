"""AgentCore Platform v1.0"""

# Deterministic (non-LLM) regulated-PII pattern scan for text fields that are
# NOT the audio payload itself (e.g. jurisdiction_profile, free-text notes).
# APPI 個人情報 / 個人番号 (My Number) pattern-based detection.

from __future__ import annotations

import re

# 12-digit My Number (個人番号) — deterministic pattern, not a full checksum validator.
_MY_NUMBER_RE = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")
# Email address — a common APPI 個人情報 leakage vector in free-text fields.
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# JP mobile phone number.
_PHONE_RE = re.compile(r"\b0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}\b")

_PATTERNS = (_MY_NUMBER_RE, _EMAIL_RE, _PHONE_RE)


def contains_regulated_pii(text: str | None) -> bool:
    """Deterministic (rule/pattern, non-LLM) regulated-PII detector."""
    if not text or not isinstance(text, str):
        return False
    return any(p.search(text) for p in _PATTERNS)


def mask_regulated_pii(text: str | None) -> str:
    """Deterministic (rule/pattern, non-LLM) participant-identifier masking (APPI)."""
    if not text or not isinstance(text, str):
        return text or ""
    masked = text
    for pattern in _PATTERNS:
        masked = pattern.sub("[REDACTED]", masked)
    return masked
