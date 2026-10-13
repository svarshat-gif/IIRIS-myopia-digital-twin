"""Evidence / RAG endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.access import admin
from app.db.database import get_db
from app.db.models import Evidence
from app.evidence import retriever

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/search", summary="Search the literature and cache the citations")
def search(q: str = Query(..., min_length=3, max_length=300),
           limit: int = Query(5, ge=1, le=25),
           prefer: str = Query("europe_pmc", pattern="^(europe_pmc|pubmed)$"),
           db: Session = Depends(get_db)) -> dict[str, Any]:
    return retriever.retrieve(db, q, limit=limit, prefer=prefer)


@router.get("/cached", summary="Citations already retrieved and stored")
def cached(limit: int = Query(50, ge=1, le=500),
           db: Session = Depends(get_db), user=Depends(admin)) -> dict[str, Any]:
    rows = db.scalars(
        select(Evidence).order_by(Evidence.retrieved_at.desc()).limit(limit)).all()
    return {"evidence": [
        {"evidence_id": r.evidence_id, "query": r.query, "source": r.source,
         "external_id": r.external_id, "title": r.title, "journal": r.journal,
         "year": r.year, "doi": r.doi, "url": r.url,
         "retrieved_at": r.retrieved_at.isoformat()}
        for r in rows
    ]}


@router.get("/status", summary="Which evidence backend is in use")
def status() -> dict[str, Any]:
    return {
        "offline_mode": settings.evidence_offline,
        "primary": "Europe PMC REST",
        "secondary": "PubMed E-utilities",
        "fallback": "bundled local corpus",
        "europe_pmc_base_url": settings.europe_pmc_base_url,
        "ncbi_api_key_configured": bool(settings.ncbi_api_key),
    }
