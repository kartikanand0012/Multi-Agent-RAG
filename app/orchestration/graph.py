"""LangGraph orchestration for the 4-agent pipeline.

State machine:
  START → intent → retrieval → reasoning → validation → END
                                               ↓ (fail, retry_count < 2)
                                           reasoning (with feedback)

The graph is compiled once at startup and reused for all queries.
"""
from __future__ import annotations

import logging
from typing import Annotated, List, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agents.intent_agent import IntentAgent, IntentResult
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.validation_agent import ValidationAgent, ValidationResult
from app.core.tracing import get_current_trace_id, get_observe_decorator, set_trace_io
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.grader import GradeResult
from app.retrieval.vector_store import VectorStore, vector_store, DEFAULT_NOTEBOOK

logger = logging.getLogger(__name__)
observe = get_observe_decorator()

MAX_RETRIES = 2


# ── State ────────────────────────────────────────────────────────────────────

class RAGState(TypedDict):
    query: str
    notebook_id: str
    intent: Optional[IntentResult]
    chunks: List[GradeResult]
    draft_response: str
    validation: Optional[ValidationResult]
    retry_count: int
    final_response: str
    trace_id: Optional[str]
    error: Optional[str]


# ── Node functions ────────────────────────────────────────────────────────────

async def run_intent(state: RAGState, agents: dict) -> RAGState:
    try:
        intent = await agents["intent"].run(state["query"])
        return {**state, "intent": intent}
    except Exception as e:
        logger.error(f"Intent agent failed: {e}")
        from app.agents.intent_agent import IntentResult
        return {**state, "intent": IntentResult("factual_lookup", [state["query"]], False, 0.5)}


async def run_retrieval(state: RAGState, agents: dict) -> RAGState:
    try:
        chunks = await agents["retrieval"].run(
            state["intent"], notebook_id=state["notebook_id"]
        )
        return {**state, "chunks": chunks}
    except Exception as e:
        logger.error(f"Retrieval agent failed: {e}")
        return {**state, "chunks": [], "error": str(e)}


async def run_reasoning(state: RAGState, agents: dict) -> RAGState:
    try:
        # On retry, append validation feedback to query for self-correction
        query = state["query"]
        if state["retry_count"] > 0 and state.get("validation"):
            feedback = state["validation"].feedback
            query = f"{query}\n\n[Previous attempt failed validation. Feedback: {feedback}]"

        response = await agents["reasoning"].run(query, state["intent"], state["chunks"])
        return {**state, "draft_response": response}
    except Exception as e:
        logger.error(f"Reasoning agent failed: {e}")
        return {**state, "draft_response": f"Error generating response: {e}", "error": str(e)}


async def run_validation(state: RAGState, agents: dict) -> RAGState:
    try:
        result = await agents["validation"].run(state["draft_response"], state["chunks"])
        return {**state, "validation": result}
    except Exception as e:
        logger.error(f"Validation agent failed: {e}")
        from app.agents.validation_agent import ValidationResult
        return {**state, "validation": ValidationResult(True, [], f"Validation error: {e}", 0.5)}


def decide_after_validation(state: RAGState) -> str:
    """Edge function: retry reasoning or finish."""
    validation = state.get("validation")
    retry_count = state.get("retry_count", 0)

    if validation and not validation.passed and retry_count < MAX_RETRIES:
        logger.info(f"Validation failed — retry {retry_count + 1}/{MAX_RETRIES}")
        return "retry"
    return "finish"


def apply_retry(state: RAGState) -> RAGState:
    """Increment retry counter before looping back to reasoning."""
    return {**state, "retry_count": state["retry_count"] + 1}


def finalise(state: RAGState) -> RAGState:
    """Build the final response, adding disclaimer if validation never passed."""
    response = state["draft_response"]
    validation = state.get("validation")

    if validation and not validation.passed:
        disclaimer = (
            "\n\n---\n*Note: This response could not be fully verified against "
            "the source documents. Please review with caution.*"
        )
        response = response + disclaimer

    # Push trace output
    set_trace_io(output=response)

    return {**state, "final_response": response}


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(
    vs: VectorStore | None = None,
    bm25: BM25Retriever | None = None,
) -> "CompiledGraph":
    """Build and compile the LangGraph state machine."""
    vs = vs or vector_store
    bm25 = bm25 or BM25Retriever()

    agents = {
        "intent": IntentAgent(),
        "retrieval": RetrievalAgent(vs, bm25),
        "reasoning": ReasoningAgent(),
        "validation": ValidationAgent(),
    }

    # Bind agents into node closures
    async def intent_node(state): return await run_intent(state, agents)
    async def retrieval_node(state): return await run_retrieval(state, agents)
    async def reasoning_node(state): return await run_reasoning(state, agents)
    async def validation_node(state): return await run_validation(state, agents)
    def retry_node(state): return apply_retry(state)
    def finalise_node(state): return finalise(state)

    graph = StateGraph(RAGState)
    graph.add_node("run_intent", intent_node)
    graph.add_node("run_retrieval", retrieval_node)
    graph.add_node("run_reasoning", reasoning_node)
    graph.add_node("run_validation", validation_node)
    graph.add_node("run_retry", retry_node)
    graph.add_node("run_finalise", finalise_node)

    graph.add_edge(START, "run_intent")
    graph.add_edge("run_intent", "run_retrieval")
    graph.add_edge("run_retrieval", "run_reasoning")
    graph.add_edge("run_reasoning", "run_validation")
    graph.add_conditional_edges(
        "run_validation",
        decide_after_validation,
        {"retry": "run_retry", "finish": "run_finalise"},
    )
    graph.add_edge("run_retry", "run_reasoning")
    graph.add_edge("run_finalise", END)

    return graph.compile()


# ── Public query function ─────────────────────────────────────────────────────

_compiled_graph = None


def get_graph() -> "CompiledGraph":
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


@observe(name="agentic_rag_pipeline")
async def query(
    user_query: str,
    notebook_id: str = DEFAULT_NOTEBOOK,
) -> dict:
    """
    Entry point for a complete RAG query.
    Returns dict with final_response, intent, validation, trace_id.
    """
    set_trace_io(input={"query": user_query, "notebook_id": notebook_id})

    initial_state: RAGState = {
        "query": user_query,
        "notebook_id": notebook_id,
        "intent": None,
        "chunks": [],
        "draft_response": "",
        "validation": None,
        "retry_count": 0,
        "final_response": "",
        "trace_id": get_current_trace_id(),
        "error": None,
    }

    final_state = await get_graph().ainvoke(initial_state)

    return {
        "response": final_state["final_response"],
        "intent_type": final_state["intent"].intent_type if final_state["intent"] else "unknown",
        "sources_used": len(final_state["chunks"]),
        "validation_passed": final_state["validation"].passed if final_state["validation"] else False,
        "retry_count": final_state["retry_count"],
        "trace_id": final_state["trace_id"],
    }
