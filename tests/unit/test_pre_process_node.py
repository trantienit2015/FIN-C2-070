import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.pre_process_node import PreProcessNode


class TestPreProcessNode:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_success_path(self):
        user_input = json.dumps({"audio_path": "call_20260713.wav", "jurisdiction_profile": "jp_fiea_37_3"})
        result = self.node.execute({"user_input": user_input})
        assert result["status"] == AgentStatus.SUCCESS
        assert result["audio_path"] == "call_20260713.wav"
        assert result["jurisdiction_profile"] == "jp_fiea_37_3"
        assert json.loads(result["validated_input"])["audio_path"] == "call_20260713.wav"

    def test_missing_audio_path_rejected(self):
        result = self.node.execute({"user_input": json.dumps({})})
        assert result["status"] == AgentStatus.ERROR
        assert result["error_log"]

    def test_non_mp3_wav_format_rejected(self):
        result = self.node.execute({"user_input": json.dumps({"audio_path": "call.txt"})})
        assert result["status"] == AgentStatus.ERROR

    def test_empty_input_no_raise(self):
        result = self.node.execute({"user_input": ""})
        assert result["status"] == AgentStatus.ERROR

    def test_pii_in_jurisdiction_profile_rejected(self):
        result = self.node.execute(
            {"user_input": json.dumps({"audio_path": "call.wav", "jurisdiction_profile": "contact me at a@b.com"})}
        )
        assert result["status"] == AgentStatus.ERROR

    def test_extra_security_gate_input_blocks_pii(self):
        out = self.node._extra_security_gate_input({"user_input": "my number is 1234-5678-9012"})
        assert out["status"] == AgentStatus.ERROR

    def test_extra_security_gate_input_passes_clean_state(self):
        state = {"user_input": json.dumps({"audio_path": "call.wav"})}
        out = self.node._extra_security_gate_input(state)
        assert out is state


class TestPreProcessTranscript:
    def test_valid_transcript_passed_through(self):
        payload = {
            "audio_path": "call.wav",
            "transcript": [{"speaker": "advisor", "text": "リスクがあります", "start_ts": 0.0, "end_ts": 1.0}],
        }
        result = PreProcessNode().execute({"user_input": json.dumps(payload)})
        assert result["status"] == AgentStatus.SUCCESS.value
        assert json.loads(result["validated_input"])["transcript"][0]["text"] == "リスクがあります"

    def test_malformed_transcript_rejected(self):
        for bad in ([], "text", [{"speaker": "a"}], [{"text": "x", "start_ts": "0"}], [{"text": "x" * 2001}]):
            payload = {"audio_path": "call.wav", "transcript": bad}
            result = PreProcessNode().execute({"user_input": json.dumps(payload)})
            assert result["status"] == AgentStatus.ERROR.value, bad

    def test_oversized_transcript_rejected(self):
        payload = {"audio_path": "call.wav", "transcript": [{"text": "x"}] * 501}
        result = PreProcessNode().execute({"user_input": json.dumps(payload)})
        assert result["status"] == AgentStatus.ERROR.value
