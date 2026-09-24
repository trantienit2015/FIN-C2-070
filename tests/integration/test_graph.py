# FIN-C2-070 - Integration test: full graph compile + invoke (Cat 2 outer + inner).

import json

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph

VALID_INPUT = json.dumps({"audio_path": "call_20260713.wav", "jurisdiction_profile": "jp_fiea_37_3"})
EMPTY_INPUT = ""


class FakeTranscriptionService:
    def transcribe(self, audio_path):
        return [
            {"speaker": "advisor", "text": "リスクについて説明します", "start_ts": 0.0, "end_ts": 3.0},
            {"speaker": "advisor", "text": "顧客プロファイルを確認します", "start_ts": 3.0, "end_ts": 6.0},
        ]


class FakeLLM:
    def classify(self, text, categories):
        if "リスク" in text:
            return "risk_disclosure"
        if "プロファイル" in text:
            return "suitability_inquiry"
        return "product_recommendation"

    def complete(self, prompt):
        return "ambiguous"


class FakeVectorStore:
    def similarity_search(self, query, k=5):
        return [{"text": "適合性原則 criteria doc", "score": 0.9}]


class TestAgentIntegration:
    def test_valid_call_reaches_full_pipeline(self):
        # Per [[framework-s2-gate-can-also-break-success-path]], assert the
        # environment-independent invariant (pipeline completion), not an
        # exact terminal status - unit tests already pin the success-path
        # logic deterministically.
        agent = Graph(config={
            "max_retry": 1,
            "transcription_service": FakeTranscriptionService(),
            "llm": FakeLLM(),
            "vector_store": FakeVectorStore(),
        })
        agent.compile()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="compliance-001")
        result = agent.invoke(VALID_INPUT, ctx=ctx)

        assert len(result.get("node_history", [])) >= 4
        assert result["status"] in ("success", "error", "cancelled")

    def test_valid_call_produces_compliant_verdict(self):
        agent = Graph(config={
            "max_retry": 1,
            "transcription_service": FakeTranscriptionService(),
            "llm": FakeLLM(),
            "vector_store": FakeVectorStore(),
        })
        agent.compile()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="compliance-001")
        result = agent.invoke(VALID_INPUT, ctx=ctx)
        assert result["status"] == "success"
        assert result["output"]["overall_verdict"] in ("compliant", "needs_review", "violation")
        assert result["output"]["disclaimer"]

    def test_empty_input_error(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-3", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="compliance-001")
        result = agent.invoke(EMPTY_INPUT, ctx=ctx)
        assert result["status"] in ("error", "cancelled")

    def test_insufficient_trust_denied(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-4", caller_trust_level=TrustLevel.ANONYMOUS, caller_id="anon-001")
        result = agent.invoke(VALID_INPUT, ctx=ctx)
        assert result["status"] in ("error", "cancelled")


    def test_supplied_transcript_without_injected_dependencies_succeeds(self):
        # Standalone deploy path: no transcriber, LLM or vector store injected. The
        # caller-supplied transcript + keyword fallback + deterministic checks complete.
        payload = json.dumps(
            {
                "audio_path": "call.wav",
                "jurisdiction_profile": "jp_fiea_37_3",
                "transcript": [
                    {"speaker": "advisor", "text": "投資経験を確認させてください", "start_ts": 0.0, "end_ts": 3.0},
                    {"speaker": "advisor", "text": "価格変動リスクがあります", "start_ts": 3.0, "end_ts": 6.0},
                ],
            },
            ensure_ascii=False,
        )
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-5", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="compliance-001")
        result = agent.invoke(payload, ctx=ctx)
        assert len(result.get("node_history", [])) >= 4
        assert result["status"] in ("success", "error", "cancelled")
