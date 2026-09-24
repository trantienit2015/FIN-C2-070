# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: AdvisoryCallComplianceGraph
- **L1 Base**: AgentBaseGraph (outer) + GraphNode(main) wrapping inner BaseGraph (Cat 2)
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Cat 2 pipeline — outer `AgentBaseGraph` backbone + `main` slot wraps an inner `BaseGraph`
subgraph (`src/graph/domain_workflow_graph.py`) that runs the 3 domain steps.

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | framework default | — | — | InitializeNode (default) |
| pre_process (ValidateInput) | audio-format deterministic gate + S-2 PII auto-reject; sets validated_input | user_input (JSON: audio_path, jurisdiction_profile) | audio_path, jurisdiction_profile, validated_input | FunctionNode |
| main (AdvisoryCallGraphNode → inner subgraph) | dispatch to inner: transcribe/diarize → classify → retrieve+check | validated_input | diarized_transcript, utterance_classifications, compliance_findings | GraphNode wrapping inner BaseGraph |
| ↳ inner: transcribe_diarize | audio → timestamped, diarized, APPI-masked transcript | audio_path | diarized_transcript | FunctionNode (inner, ANONYMOUS) |
| ↳ inner: classify_utterances | LLM classifies each utterance (4 categories); with no LLM configured, a deterministic keyword baseline labelled `method: keyword_fallback` | diarized_transcript | utterance_classifications | FunctionNode (inner, ANONYMOUS) |
| ↳ inner: retrieve_and_check_compliance | KB retrieval + deterministic mandatory-item/forbidden-phrase matchers | utterance_classifications | compliance_findings | FunctionNode (inner, ANONYMOUS) |
| post_process (GenerateVerdict) | compose per-dimension verdict + mandatory disclaimer (S-3) + cleanup temp audio | compliance_findings, audio_path | verdict_report, formatted_output | FunctionNode |
| finalize | framework default | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process(ValidateInput) → main(AdvisoryCallGraphNode)
       → {route} → post_process(GenerateVerdict) → finalize → END
                                            ↓ (retry)
                                          pre_process

Inner (inside main): START → transcribe_diarize → classify_utterances
                            → retrieve_and_check_compliance → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| audio_path | NotRequired[str] | temp path to the submitted MP3/WAV recording | no |
| jurisdiction_profile | NotRequired[str] | suitability ruleset selector (config-derived default) | no |
| diarized_transcript | NotRequired[list[dict]] | timestamped, speaker-diarized, APPI-masked transcript | no |
| utterance_classifications | NotRequired[list[dict]] | diarized_transcript + per-utterance category | no |
| compliance_findings | NotRequired[list[dict]] | per-dimension verdict + evidence timestamps | no |
| verdict_report | NotRequired[dict] | assembled verdict report incl. mandatory disclaimer | no |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- Raw audio bytes are never stored in State — only the temp `audio_path` string.

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, caller_trust_level)
- [x] SecurityViolationError-equivalent fail-closed ERROR dict (non-raising per hook contract)
- [x] S-2: `_extra_security_gate_input()` on `ValidateInput` (pre_process) — deterministic
      regulated-PII (APPI 個人情報 / 個人番号) pattern scan on raw `user_input` (non-audio fields)
- [x] S-3: `_extra_security_gate_output()` on `GenerateVerdict` (post_process) — preservation
      variant: verifies the mandatory non-advice disclaimer is present in `verdict_report`
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside every node's
      `execute()` (outer + inner), plus dispatch/completion events in the GraphNode
      `extract_input()`/`merge_output()` hooks

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — Cat 2, `main` slot wraps `AdvisoryCallWorkflowGraph`
- **Composition target**: `src/graph/domain_workflow_graph.py::AdvisoryCallWorkflowGraph`
- **Error propagation strategy**: propagate (`error_strategy="propagate"` — fail fast; no HITL)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph (outer) | Fixed 4-stage audit pipeline — no autonomous reasoning loop needed |
| Composition pattern | Flat 3-node (Cat 1 style) | GraphNode + inner subgraph | GraphNode + inner subgraph | Cat 2 requires outer/GraphNode/inner split (`gate-composition`); 3 domain steps live in the inner graph |
| Deterministic vs LLM split | All-LLM classification | Deterministic matchers + LLM only for classification/gray-zone | Deterministic matchers + LLM | 適合性原則 mandatory-item / 断定的判断 forbidden-phrase checks are rule-expressible; LLM reserved for utterance-category judgment (context-dependent) |

## Degraded Operation (optional dependencies absent)

`transcription_service`, `llm` and `vector_store` are injected through `Graph(config=...)`. The
standalone entry point injects none of them, apart from an LLM when `ANTHROPIC_API_KEY` is set.
Each node handles an absent dependency explicitly:

| Node | Dependency absent | Behaviour |
|------|-------------------|-----------|
| ValidateInput | — | Accepts an optional `transcript` list (bounded: ≤500 utterances, text ≤2,000 chars, numeric timestamps) and forwards it in `validated_input` |
| TranscribeDiarize | `transcription_service` | Uses the caller-supplied `transcript` (same PII masking); without one → `status: error`. Trace records `transcript_source` |
| ClassifyUtterances | `llm` | Deterministic keyword baseline; every classification labelled `method: keyword_fallback`. An injected client may expose `classify(text, categories)` or the BaseLLM `complete(messages)` contract |
| RetrieveAndCheckCompliance | `vector_store` | Retrieval skipped (trace `retrieval: skipped_no_vector_store`); deterministic mandatory-item and forbidden-phrase checks run unchanged |

The fallback path lets the pipeline complete for a deploy check. It does not replace the LLM
intent judgment or the curated compliance KB.
