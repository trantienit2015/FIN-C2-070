from framework.schemas.agent_status import AgentStatus
from src.nodes import classify_utterances_node
from src.nodes.classify_utterances_node import ClassifyUtterancesNode


class FakeLLM:
    def classify(self, text, categories):
        return "risk_disclosure" if "risk" in text.lower() or "リスク" in text else "suitability_inquiry"


class TestClassifyUtterancesNode:
    def test_success_path(self):
        node = ClassifyUtterancesNode(llm=FakeLLM())
        state = {
            "diarized_transcript": [
                {"speaker": "advisor", "text": "risk disclosure text", "start_ts": 0.0, "end_ts": 1.0},
            ],
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["utterance_classifications"][0]["category"] == "risk_disclosure"

    def test_no_llm_configured_uses_labelled_keyword_fallback(self, monkeypatch):
        events = []
        monkeypatch.setattr(classify_utterances_node, "emit_trace_event", lambda e, p, s: events.append((e, p)))
        node = ClassifyUtterancesNode()
        result = node.execute(
            {
                "diarized_transcript": [
                    {"text": "価格変動リスクがあります", "start_ts": 0.0},
                    {"text": "投資経験を確認します", "start_ts": 1.0},
                    {"text": "少し不安です", "start_ts": 2.0},
                    {"text": "こちらの商品をご提案します", "start_ts": 3.0},
                ]
            }
        )
        assert result["status"] == AgentStatus.SUCCESS.value
        cats = [c["category"] for c in result["utterance_classifications"]]
        assert cats == ["risk_disclosure", "suitability_inquiry", "customer_objection", "product_recommendation"]
        assert {c["method"] for c in result["utterance_classifications"]} == {"keyword_fallback"}
        assert events[-1][0] == "utterances_classified"
        assert events[-1][1]["method"] == "keyword_fallback"

    def test_base_llm_complete_contract_is_supported(self):
        class CompleteOnlyLLM:
            def complete(self, messages):
                assert messages and messages[0]["role"] == "user"
                return {"content": "suitability_inquiry", "tool_calls": [], "model": "fake", "usage": {}}

        node = ClassifyUtterancesNode(llm=CompleteOnlyLLM())
        result = node.execute({"diarized_transcript": [{"text": "anything", "start_ts": 0.0}]})
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["utterance_classifications"][0]["category"] == "suitability_inquiry"
        assert result["utterance_classifications"][0]["method"] == "llm"

    def test_empty_transcript(self, monkeypatch):
        events = []
        monkeypatch.setattr(classify_utterances_node, "emit_trace_event", lambda e, p, s: events.append(e))
        node = ClassifyUtterancesNode(llm=FakeLLM())
        result = node.execute({"diarized_transcript": []})
        assert result["status"] == AgentStatus.ERROR
        assert "utterance_classification_rejected" in events
