"""AgentCore Platform v1.0"""

# Deterministic (non-LLM) matchers for the 適合性原則 (金商法 37条の3) mandatory-item
# checklist and the 断定的判断 forbidden-phrase list. LLM interpretation is reserved
# for ambiguous/gray-zone utterances only (see RetrieveAndCheckComplianceNode).

from __future__ import annotations

from typing import Any

MANDATORY_ITEMS = (
    "risk_explained",
    "customer_profile_confirmed",
)

# 断定的判断 (definitive-judgment) forbidden phrases — deterministic substring match.
FORBIDDEN_PHRASES = (
    "絶対に儲かります",
    "必ず値上がりします",
    "元本保証",
    "リスクはありません",
)


def check_mandatory_items(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic presence check for each mandatory suitability item.

    utterances: list of {"speaker": str, "text": str, "category": str, "start_ts": float, "end_ts": float}
    Returns one finding dict per mandatory item.
    """
    joined = " ".join(u.get("text", "") for u in utterances)
    findings = []
    risk_present = any(u.get("category") == "risk_disclosure" for u in utterances)
    profile_present = any(u.get("category") == "suitability_inquiry" for u in utterances)
    findings.append(
        {
            "dimension": "risk_explained",
            "present": risk_present,
            "evidence_timestamps": [u["start_ts"] for u in utterances if u.get("category") == "risk_disclosure"],
        }
    )
    findings.append(
        {
            "dimension": "customer_profile_confirmed",
            "present": profile_present,
            "evidence_timestamps": [u["start_ts"] for u in utterances if u.get("category") == "suitability_inquiry"],
        }
    )
    _ = joined  # reserved for future substring-based mandatory-item checks
    return findings


def check_forbidden_phrases(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic substring match for 断定的判断 forbidden phrases."""
    hits = []
    for u in utterances:
        text = u.get("text", "")
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                hits.append(
                    {
                        "phrase": phrase,
                        "speaker": u.get("speaker"),
                        "start_ts": u.get("start_ts"),
                    }
                )
    return hits
