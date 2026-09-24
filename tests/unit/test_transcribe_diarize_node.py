import json

from framework.schemas.agent_status import AgentStatus
from src.nodes import transcribe_diarize_node
from src.nodes.transcribe_diarize_node import TranscribeDiarizeNode


class FakeTranscriptionService:
    def transcribe(self, audio_path):
        return [
            {"speaker": "advisor", "text": "リスクについて説明します", "start_ts": 0.0, "end_ts": 3.0},
            {"speaker": "customer", "text": "email me at a@b.com please", "start_ts": 3.0, "end_ts": 5.0},
        ]


class EmptyTranscriptionService:
    def transcribe(self, audio_path):
        return []


class TestTranscribeDiarizeNode:
    def test_success_path_masks_pii(self):
        node = TranscribeDiarizeNode(transcription_service=FakeTranscriptionService())
        state = {"user_input": json.dumps({"audio_path": "call.wav"})}
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert len(result["diarized_transcript"]) == 2
        assert "a@b.com" not in result["diarized_transcript"][1]["text"]
        assert "[REDACTED]" in result["diarized_transcript"][1]["text"]

    def test_no_transcription_service_configured(self, monkeypatch):
        events = []
        monkeypatch.setattr(transcribe_diarize_node, "emit_trace_event", lambda e, p, s: events.append(e))
        node = TranscribeDiarizeNode()
        result = node.execute({"user_input": json.dumps({"audio_path": "call.wav"})})
        assert result["status"] == AgentStatus.ERROR
        assert "call_transcription_rejected" in events

    def test_empty_transcription_result(self, monkeypatch):
        events = []
        monkeypatch.setattr(transcribe_diarize_node, "emit_trace_event", lambda e, p, s: events.append(e))
        node = TranscribeDiarizeNode(transcription_service=EmptyTranscriptionService())
        result = node.execute({"user_input": json.dumps({"audio_path": "call.wav"})})
        assert result["status"] == AgentStatus.ERROR
        assert "call_transcription_rejected" in events


class TestTranscribeDiarizeSuppliedTranscript:
    def test_supplied_transcript_used_when_no_service_and_masked(self, monkeypatch):
        events = []
        monkeypatch.setattr(transcribe_diarize_node, "emit_trace_event", lambda e, p, s: events.append((e, p)))
        node = TranscribeDiarizeNode()
        payload = {
            "audio_path": "call.wav",
            "transcript": [
                {"speaker": "advisor", "text": "リスクについて説明します", "start_ts": 0.0, "end_ts": 3.0},
                {"speaker": "customer", "text": "email me at a@b.com please", "start_ts": 3.0, "end_ts": 5.0},
            ],
        }
        result = node.execute({"user_input": json.dumps(payload)})
        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["diarized_transcript"]) == 2
        assert "a@b.com" not in result["diarized_transcript"][1]["text"]
        assert events[-1][1]["transcript_source"] == "caller_supplied_transcript"

    def test_service_takes_precedence_over_supplied_transcript(self):
        node = TranscribeDiarizeNode(transcription_service=FakeTranscriptionService())
        payload = {"audio_path": "call.wav", "transcript": [{"text": "ignored"}]}
        result = node.execute({"user_input": json.dumps(payload)})
        assert result["diarized_transcript"][0]["text"] == "リスクについて説明します"
