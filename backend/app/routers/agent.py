"""Agentic endpoints: ask a question, inspect the tools, inspect the graph."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import graph, llm
from app.agents.tools import tool_schemas
from app.core.config import settings
from app.db.database import get_db
from app.db.models import AgentRun
from app.schemas.models import AgentQueryIn

router = APIRouter(tags=["agent"])


@router.get("/agent/tools", summary="The tools the agent is allowed to call")
def list_tools() -> dict[str, Any]:
    return {
        "tools": tool_schemas(),
        "note": "The agent can obtain facts ONLY through these tools. Anything it "
                "states is traceable to one of them.",
    }


@router.get("/agent/graph", summary="The agent graph, read from the running code")
def agent_graph() -> dict[str, Any]:
    return graph.graph_spec()


@router.get("/agent/status", summary="Which LLM (if any) is attached")
def agent_status() -> dict[str, Any]:
    return {
        "llm_enabled": llm.is_enabled(),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model if llm.is_enabled() else None,
        "guardrail": "Every number in a generated answer must be traceable to tool "
                     "output, or the generated text is discarded.",
        "works_without_llm": True,
    }


@router.post("/patients/{patient_id}/query", summary="Ask the agent about one patient")
def query_patient(patient_id: str, payload: AgentQueryIn,
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    return _run(db, payload.question, patient_id)


@router.post("/agent/query", summary="Ask the agent (patient optional)")
def query(payload: AgentQueryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _run(db, payload.question, payload.patient_id)


def _run(db: Session, question: str, patient_id: str | None) -> dict[str, Any]:
    try:
        result = graph.run(db, question, patient_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Agent failed: {type(exc).__name__}: {exc}") from exc

    run = AgentRun(
        patient_id=patient_id,
        question=question,
        plan_json={"intent": result["intent"], "plan": result["plan"]},
        trace_json={"trace": result["trace"], "issues": result["issues"],
                    "guardrail": result["guardrail"]},
        answer=result["answer"],
        llm_used=result["llm_used"],
    )
    db.add(run)
    db.commit()
    return {"run_id": run.run_id, **result}


@router.get("/agent/runs", summary="Audit trail of previous agent answers")
def list_runs(db: Session = Depends(get_db),
              patient_id: str | None = None,
              limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if patient_id:
        stmt = stmt.where(AgentRun.patient_id == patient_id)
    rows = db.scalars(stmt).all()
    return {"runs": [
        {"run_id": r.run_id, "patient_id": r.patient_id, "question": r.question,
         "answer": r.answer, "llm_used": r.llm_used,
         "tools_called": [t["tool"] for t in r.trace_json.get("trace", [])
                          if t.get("status") == "ok"],
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]}
