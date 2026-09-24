"""AgentCore Platform v1.0"""

# Inner graph for the Cat 2 advisory-call compliance workflow. Instantiated by
# AdvisoryCallGraphNode.get_subgraph() in src/graph/graph.py.
#
# Pipeline: START → transcribe_diarize → classify_utterances →
#           retrieve_and_check_compliance → END

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.classify_utterances_node import ClassifyUtterancesNode
from src.nodes.retrieve_and_check_compliance_node import RetrieveAndCheckComplianceNode
from src.nodes.transcribe_diarize_node import TranscribeDiarizeNode
from src.schemas.state import State


class AdvisoryCallWorkflowGraph(BaseGraph):
    """Inner graph: transcribe/diarize -> classify -> retrieve+check compliance."""

    @property
    def name(self) -> str:
        return "advisory_call_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        transcription_service = self.config.get("transcription_service")
        llm = self.config.get("llm")
        vector_store = self.config.get("vector_store")
        top_k = self.config.get("top_k", 5)

        self._nodes["transcribe_diarize"] = TranscribeDiarizeNode(transcription_service=transcription_service)
        self._nodes["classify_utterances"] = ClassifyUtterancesNode(llm=llm)
        self._nodes["retrieve_and_check_compliance"] = RetrieveAndCheckComplianceNode(
            vector_store=vector_store, llm=llm, top_k=top_k
        )

    def add_edges(self) -> None:
        self._sg.add_edge(START, "transcribe_diarize")
        self._sg.add_edge("transcribe_diarize", "classify_utterances")
        self._sg.add_edge("classify_utterances", "retrieve_and_check_compliance")
        self._sg.add_edge("retrieve_and_check_compliance", END)

    def route(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "retrieve_and_check_compliance"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "diarized_transcript": state.get("diarized_transcript", []),
            "utterance_classifications": state.get("utterance_classifications", []),
            "compliance_findings": state.get("compliance_findings", []),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
