"""Evidence retrieval: Europe PMC (primary), PubMed E-utilities (secondary),
local corpus (fallback).

Retrieved records are cached in the `evidence` table so every agent answer can
cite a stored, timestamped source rather than a live re-query.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Evidence
from app.evidence import corpus

log = logging.getLogger(__name__)

# Appended to user queries so retrieval stays on-topic.
TOPIC_FILTER = "myopia"


def _ensure_topic(query: str) -> str:
    return query if TOPIC_FILTER in query.lower() else f"{query} {TOPIC_FILTER}"


def search_europe_pmc(query: str, limit: int = 5) -> list[dict[str, Any]]:
    params = {
        "query": _ensure_topic(query),
        "format": "json",
        "pageSize": limit,
        "resultType": "core",
        "sort": "CITED desc",
    }
    with httpx.Client(timeout=settings.evidence_timeout_seconds) as client:
        r = client.get(f"{settings.europe_pmc_base_url}/search", params=params)
        r.raise_for_status()
        payload = r.json()

    results: list[dict[str, Any]] = []
    for item in payload.get("resultList", {}).get("result", []):
        pmid = item.get("pmid")
        pmcid = item.get("pmcid")
        ext = f"PMID:{pmid}" if pmid else (f"PMCID:{pmcid}" if pmcid else item.get("id"))
        url = (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else
               f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}")
        results.append({
            "source": "europe_pmc",
            "external_id": ext,
            "title": item.get("title", "").strip(),
            "abstract": (item.get("abstractText") or "")[:2000] or None,
            "authors": item.get("authorString"),
            "journal": item.get("journalTitle"),
            "year": str(item.get("pubYear")) if item.get("pubYear") else None,
            "doi": item.get("doi"),
            "url": url,
            "citations": item.get("citedByCount"),
            "open_access": item.get("isOpenAccess") == "Y",
        })
    return results


def search_pubmed(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """NCBI E-utilities: esearch -> esummary."""
    base_params: dict[str, Any] = {"db": "pubmed", "retmode": "json"}
    if settings.ncbi_api_key:
        base_params["api_key"] = settings.ncbi_api_key
    if settings.evidence_contact_email:
        base_params["email"] = settings.evidence_contact_email
        base_params["tool"] = "myopia-digital-twin"

    with httpx.Client(timeout=settings.evidence_timeout_seconds) as client:
        r = client.get(f"{settings.pubmed_base_url}/esearch.fcgi",
                       params={**base_params, "term": _ensure_topic(query),
                               "retmax": limit, "sort": "relevance"})
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        r = client.get(f"{settings.pubmed_base_url}/esummary.fcgi",
                       params={**base_params, "id": ",".join(ids)})
        r.raise_for_status()
        summaries = r.json().get("result", {})

    results = []
    for pmid in ids:
        item = summaries.get(pmid)
        if not item:
            continue
        doi = next((x.get("value") for x in item.get("articleids", [])
                    if x.get("idtype") == "doi"), None)
        results.append({
            "source": "pubmed",
            "external_id": f"PMID:{pmid}",
            "title": item.get("title", "").strip(),
            "abstract": None,  # esummary has no abstract; efetch would be needed
            "authors": ", ".join(a.get("name", "") for a in item.get("authors", [])[:6]),
            "journal": item.get("fulljournalname") or item.get("source"),
            "year": (item.get("pubdate") or "")[:4] or None,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return results


def retrieve(db: Session | None, query: str, limit: int = 5,
             prefer: str = "europe_pmc") -> dict[str, Any]:
    """Retrieve evidence with graceful degradation, then cache it.

    Never raises on network failure: the local corpus keeps the demo working
    offline, and the response always states which source was actually used.
    """
    notes: list[str] = []
    results: list[dict[str, Any]] = []
    used = "local_corpus"

    if not settings.evidence_offline:
        order = (["europe_pmc", "pubmed"] if prefer == "europe_pmc"
                 else ["pubmed", "europe_pmc"])
        for source in order:
            try:
                fn = search_europe_pmc if source == "europe_pmc" else search_pubmed
                results = fn(query, limit)
                if results:
                    used = source
                    break
                notes.append(f"{source} returned no results.")
            except Exception as exc:  # network, rate limit, schema change
                log.warning("Evidence source %s failed: %s", source, exc)
                notes.append(f"{source} unavailable ({type(exc).__name__}).")
    else:
        notes.append("EVIDENCE_OFFLINE=true; using the bundled corpus only.")

    if not results:
        results = corpus.search(query, limit)
        used = "local_corpus"
        notes.append(
            "Falling back to the small bundled corpus. These are real citations but a "
            "deliberately narrow set, not a systematic search."
        )

    if db is not None:
        for item in results:
            stored = db.scalars(
                select(Evidence).where(
                    Evidence.query == query[:512],
                    Evidence.external_id == item.get("external_id"))
            ).first()
            if stored is None:
                stored = Evidence(
                    query=query[:512],
                    source=item.get("source", used),
                    external_id=item.get("external_id"),
                    title=item.get("title", ""),
                    abstract=item.get("abstract"),
                    authors=item.get("authors"),
                    journal=item.get("journal"),
                    year=item.get("year"),
                    doi=item.get("doi"),
                    url=item.get("url"),
                )
                db.add(stored)
                db.flush()
            item["evidence_id"] = stored.evidence_id
        db.commit()

    return {
        "query": query,
        "source_used": used,
        "results": results,
        "notes": notes,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "caveat": (
            "Retrieved literature is background context about myopia in general. It is "
            "not evidence about this individual patient and does not validate the "
            "model's numeric output."
        ),
    }


def evidence_query_for(topic_hints: list[str]) -> str:
    """Build a retrieval query from what the twin/simulator actually touched."""
    mapping = {
        "outdoor_min": "outdoor time myopia progression children",
        "screen_time_hours": "screen time myopia children",
        "near_work_min": "near work myopia progression",
        "viewing_distance_cm": "reading distance working distance myopia",
        "posture_score": "posture reading ergonomics myopia",
        "continuous_session_min": "continuous near work breaks myopia",
        "treatment": "myopia control treatment atropine orthokeratology DIMS",
        "axial_length": "axial length elongation children monitoring",
        "sleep_hours": "sleep duration myopia children",
    }
    parts = [mapping[h] for h in topic_hints if h in mapping]
    return " OR ".join(parts) if parts else "myopia progression children risk factors"
