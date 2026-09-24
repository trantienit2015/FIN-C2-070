from framework.schemas.agent_status import AgentStatus
from src.nodes import retrieve_and_check_compliance_node
from src.nodes.retrieve_and_check_compliance_node import RetrieveAndCheckComplianceNode


class FakeVectorStore:
    def similarity_search(self, query, k=5):
        return [{"text": "適合性原則 criteria doc", "score": 0.9}]


class FakeLLM:
    def complete(self, prompt):
        return "ambiguous"


class TestRetrieveAndCheckComplianceNode:
    def setup_method(self):
        self.node = RetrieveAndCheckComplianceNode(vector_store=FakeVectorStore(), llm=FakeLLM(), top_k=5)

    def test_success_path_compliant(self):
        utterances = [
            {"speaker": "advisor", "text": "safe recommendation", "category": "risk_disclosure", "start_ts": 1.0},
            {"speaker": "advisor", "text": "profile check", "category": "suitability_inquiry", "start_ts": 2.0},
        ]
        result = self.node.execute({"utterance_classifications": utterances})
        assert result["status"] == AgentStatus.SUCCESS
        findings = {f["dimension"]: f["verdict"] for f in result["compliance_findings"]}
        assert findings["risk_explained"] == "compliant"
        assert findings["customer_profile_confirmed"] == "compliant"
        assert findings["forbidden_phrase"] == "compliant"

    def test_forbidden_phrase_detected(self):
        utterances = [
            {"speaker": "advisor", "text": "元本保証です", "category": "product_recommendation", "start_ts": 4.0},
        ]
        result = self.node.execute({"utterance_classifications": utterances})
        findings = {f["dimension"]: f["verdict"] for f in result["compliance_findings"]}
        assert findings["forbidden_phrase"] == "violation"

    def test_missing_mandatory_items_needs_review(self):
        utterances = [
            {"speaker": "advisor", "text": "generic chat", "category": "product_recommendation", "start_ts": 1.0},
        ]
        result = self.node.execute({"utterance_classifications": utterances})
        findings = {f["dimension"]: f["verdict"] for f in result["compliance_findings"]}
        assert findings["risk_explained"] == "needs_review"

    def test_no_vector_store_skips_retrieval_runs_deterministic_checks(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            retrieve_and_check_compliance_node, "emit_trace_event", lambda e, p, s: events.append((e, p))
        )
        node = RetrieveAndCheckComplianceNode()
        utterances = [{"text": "元本保証です", "category": "product_recommendation", "start_ts": 4.0}]
        result = node.execute({"utterance_classifications": utterances})
        assert result["status"] == AgentStatus.SUCCESS.value
        findings = {f["dimension"]: f["verdict"] for f in result["compliance_findings"]}
        assert findings["forbidden_phrase"] == "violation"
        assert findings["risk_explained"] == "needs_review"
        assert events[-1][0] == "compliance_checked"
        assert events[-1][1]["retrieval"] == "skipped_no_vector_store"

    def test_empty_utterances(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            retrieve_and_check_compliance_node, "emit_trace_event", lambda e, p, s: events.append(e)
        )
        result = self.node.execute({"utterance_classifications": []})
        assert result["status"] == AgentStatus.ERROR
        assert "compliance_check_rejected" in events
