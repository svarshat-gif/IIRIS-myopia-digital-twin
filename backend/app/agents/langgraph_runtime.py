"""LangGraph execution of the agent graph.

The node functions in `app.agents.graph` are the single source of truth. This
module only supplies a different *executor* for them: instead of the built-in
loop, the same route -> plan -> execute -> check -> compose graph is compiled and
run by LangGraph.

Keeping the nodes shared means the behaviour, the audit trace and the tests are
identical under either runtime, and the deployment can fall back to the built-in
loop if LangGraph is not installed.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.agents.graph import (
    EDGES,
    ENTRY,
    NODES,
    AgentState,
)

log = logging.getLogger(__name__)

_compiled = None


def is_available() -> bool:
    # Optional graph libraries must not enable remote trace export via ambient env.
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    try:
        import langgraph  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def _wrap(fn):
    """Adapt a mutating node to LangGraph's 'return the updated fields' contract."""
    def node(state: AgentState) -> dict[str, Any]:
        updated = fn(state)
        return {
            "intent": updated.intent,
            "plan": updated.plan,
            "trace": updated.trace,
            "facts": updated.facts,
            "issues": updated.issues,
            "answer": updated.answer,
            "llm_used": updated.llm_used,
            "guardrail": updated.guardrail,
        }
    node.__name__ = fn.__name__
    return node


def build():
    """Compile the graph once and reuse it."""
    global _compiled
    if _compiled is not None:
        return _compiled

    from langgraph.graph import END, StateGraph  # noqa: PLC0415

    builder = StateGraph(AgentState)
    for name, fn in NODES.items():
        builder.add_node(name, _wrap(fn))
    builder.set_entry_point(ENTRY)
    for src, dst in EDGES:
        builder.add_edge(src, END if dst == "END" else dst)

    _compiled = builder.compile()
    return _compiled


def run(db: Session, question: str, patient_id: str | None) -> AgentState:
    """Execute the graph under LangGraph and return the final state."""
    graph = build()
    initial = AgentState(question=question, patient_id=patient_id, db=db)
    result = graph.invoke(initial)

    # LangGraph hands back the merged state; normalise it to an AgentState so the
    # caller cannot tell which runtime produced it.
    if isinstance(result, AgentState):
        return result
    final = AgentState(question=question, patient_id=patient_id, db=db)
    for key, value in (result.items() if isinstance(result, dict) else []):
        if hasattr(final, key) and key != "db":
            setattr(final, key, value)
    return final
