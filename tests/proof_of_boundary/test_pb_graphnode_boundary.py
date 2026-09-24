# PB-6 (supplementary) — GraphNode boundary verification for the Cat 2 outer `main` slot.
#
# PB-6 (test_pb_invoke_order.py) only auto-discovers BaseNode subclasses under
# src/nodes/. AdvisoryCallGraphNode is (correctly, per scaffold canonical) defined
# in src/graph/graph.py, so it is invisible to that discovery — leaving the
# outer GraphNode wrapper (the node that receives caller input first in this
# Cat 2 template) with no boundary test at all. This file closes that gap
# (a GraphNode is outside the standard PB-6 scope).
#
# AdvisoryCallGraphNode intentionally delegates S-2/S-3 gating to the inner
# subgraph's entry node (see framework/nodes/graph_node.py — GraphNode.__call__
# skips the standard FunctionNode security-gate lifecycle by design). This is
# architecture, not a test-avoidance shortcut — see the assertion at the bottom
# that the inner entry node still declares its own required_trust_level.

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import AdvisoryCallGraphNode
from src.nodes.transcribe_diarize_node import TranscribeDiarizeNode


class TestGraphNodeBoundary:
    """PB-6 (supplementary): S-1 trust gate + explicit field-mapping boundary for the
    outer GraphNode wrapper of this Cat 2 template."""

    def test_s1_trust_gate_denies_below_required_level(self):
        node = AdvisoryCallGraphNode()
        state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "user_input": '{"audio_path": "call.wav", "jurisdiction_profile": "jp_fiea_37_3"}',
            "node_history": [],
            "error_log": [],
        }
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert any("trust gate" in e.lower() for e in result.get("error_log", []))

    def test_extract_input_only_takes_contract_fields(self):
        node = AdvisoryCallGraphNode()
        state = {
            "validated_input": '{"audio_path": "call.wav", "jurisdiction_profile": "jp_fiea_37_3"}',
            "user_input": "should not be picked when validated_input is present",
            "unrelated_secret_field": "should never leak into extract_input()",
        }
        payload = node.extract_input(state)
        assert payload == state["validated_input"]
        assert "unrelated_secret_field" not in payload

    def test_merge_output_maps_fields_explicitly_no_raw_passthrough(self):
        node = AdvisoryCallGraphNode()
        state = {"correlation_id": "pb6-graphnode-test"}
        sub_result = {
            "diarized_transcript": [{"speaker": "advisor", "text": "hi", "start_ts": 0.0, "end_ts": 1.0}],
            "utterance_classifications": [{"speaker": "advisor", "text": "hi", "category": "risk_disclosure"}],
            "compliance_findings": [{"dimension": "risk_explained", "verdict": "compliant"}],
            "status": AgentStatus.SUCCESS.value,
            "internal_debug_trace": "must not leak into parent state",
        }
        merged = node.merge_output(state, sub_result)
        assert merged == {
            "diarized_transcript": sub_result["diarized_transcript"],
            "utterance_classifications": sub_result["utterance_classifications"],
            "compliance_findings": sub_result["compliance_findings"],
            "status": AgentStatus.SUCCESS.value,
        }
        assert "internal_debug_trace" not in merged

    def test_inner_entry_node_declares_own_trust_and_gating(self):
        """Delegation is deliberate: the inner subgraph's entry node
        (TranscribeDiarizeNode) still runs the full S-1..S-4 node
        lifecycle via BaseNode.__call__() — GraphNode only skips its OWN
        wrapper lifecycle, it does not remove security from the inner graph."""
        assert TranscribeDiarizeNode.required_trust_level == TrustLevel.ANONYMOUS
        # ANONYMOUS is correct here (not "ungated"): inner nodes trust the
        # outer boundary (this GraphNode's own S-1 check above) rather than
        # re-declaring an elevated level — see finding-recipes 3b.
