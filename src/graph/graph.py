"""AgentCore Platform v1.0"""

# FIN-C2-070 — Financial Advisory Call Compliance & Suitability Check Agent.
# Cat 2: outer AgentBaseGraph backbone + GraphNode in the `main` slot wrapping
# the inner advisory-call workflow subgraph (src/graph/domain_workflow_graph.py).
#
# Outer backbone (fixed, same as Cat 1):
#   START → initialize → pre_process(ValidateInput) → main(AdvisoryCallGraphNode)
#          → {route} → post_process(GenerateVerdict) → finalize → END
#
# Inner (domain_workflow_graph.py):
#   START → transcribe_diarize → classify_utterances → retrieve_and_check_compliance → END
#
# AdvisoryCallGraphNode is defined in THIS file (not under src/nodes/) so that
# tests/proof_of_boundary/test_pb_invoke_order.py (which auto-discovers every
# BaseNode subclass under src/nodes/) does not assert the standard node
# lifecycle on a GraphNode wrapper — GraphNode intentionally delegates gating
# to the inner subgraph.

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.pre_process_node import PreProcessNode
from src.nodes.post_process_node import PostProcessNode
from src.schemas.state import State


class AdvisoryCallGraphNode(GraphNode):
    """Wraps the inner advisory-call workflow subgraph; assigned to `main`."""

    # S-1: outer main-slot node — matches config/agent.yaml required_trust_level
    # (same as the sibling pre_process/post_process outer nodes).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, transcription_service: Any = None, llm: Any = None, vector_store: Any = None, top_k: int = 5):
        super().__init__()
        self._transcription_service = transcription_service
        self._llm = llm
        self._vector_store = vector_store
        self._top_k = top_k

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import AdvisoryCallWorkflowGraph

        sg = AdvisoryCallWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: runs inside GraphNode.execute() — audit dispatch into the inner subgraph.
        emit_trace_event(
            "advisory_call_workflow_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        # S-4: runs inside GraphNode.execute() — audit the subgraph outcome merged back out.
        emit_trace_event(
            "advisory_call_workflow_completed",
            {"finding_count": len(sub_result.get("compliance_findings", []))},
            state,
        )
        return {
            "diarized_transcript": sub_result.get("diarized_transcript", []),
            "utterance_classifications": sub_result.get("utterance_classifications", []),
            "compliance_findings": sub_result.get("compliance_findings", []),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "transcription_service": self._transcription_service,
            "llm": self._llm,
            "vector_store": self._vector_store,
            "top_k": self._top_k,
        }


class AdvisoryCallComplianceGraph(AgentBaseGraph):
    """FIN-C2-070 outer graph — Cat 2 advisory-call compliance audit pipeline."""

    @property
    def name(self) -> str:
        return "fin-c2-070"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        transcription_service = self.config.get("transcription_service")
        llm = self.config.get("llm")
        vector_store = self.config.get("vector_store")
        top_k = self.config.get("top_k", 5)

        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = AdvisoryCallGraphNode(
            transcription_service=transcription_service, llm=llm, vector_store=vector_store, top_k=top_k
        )
        self._nodes["post_process"] = PostProcessNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.


Graph = AdvisoryCallComplianceGraph  # alias for config/agent.yaml module:"src.graph"
