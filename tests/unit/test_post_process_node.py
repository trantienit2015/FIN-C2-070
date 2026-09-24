from framework.schemas.agent_status import AgentStatus
from src.nodes import post_process_node
from src.nodes.post_process_node import PostProcessNode


class TestPostProcessNode:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_success_path_compliant(self):
        state = {
            "compliance_findings": [
                {"dimension": "risk_explained", "verdict": "compliant", "evidence_timestamps": [1.0]},
                {"dimension": "customer_profile_confirmed", "verdict": "compliant", "evidence_timestamps": [2.0]},
                {"dimension": "forbidden_phrase", "verdict": "compliant", "evidence_timestamps": []},
            ],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["verdict_report"]["overall_verdict"] == "compliant"
        assert result["verdict_report"]["disclaimer"]

    def test_success_path_violation(self):
        state = {
            "compliance_findings": [
                {"dimension": "forbidden_phrase", "verdict": "violation", "evidence_timestamps": [5.0]},
            ],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["verdict_report"]["overall_verdict"] == "violation"

    def test_upstream_error_passthrough(self, monkeypatch):
        events = []
        monkeypatch.setattr(post_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        result = self.node.execute({"status": AgentStatus.ERROR, "audio_path": "call.wav"})
        assert result["status"] == AgentStatus.ERROR
        assert "compliance_verdict_skipped" in events

    def test_cleanup_called_on_missing_audio(self, tmp_path):
        audio_file = tmp_path / "call.wav"
        audio_file.write_bytes(b"fake")
        result = self.node.execute({"audio_path": str(audio_file), "compliance_findings": []})
        assert result["status"] == AgentStatus.SUCCESS
        assert not audio_file.exists()

    def test_extra_security_gate_output_blocks_missing_disclaimer(self):
        out = self.node._extra_security_gate_output(
            {"verdict_report": {"dimensions": {}, "overall_verdict": "compliant"}}
        )
        assert out["status"] == AgentStatus.ERROR

    def test_extra_security_gate_output_passes_with_disclaimer(self):
        state = {"verdict_report": {"dimensions": {}, "overall_verdict": "compliant", "disclaimer": "text"}}
        out = self.node._extra_security_gate_output(state)
        assert out is state
