"""Small curated offline corpus.

Used when the machine has no internet access (demo rooms, viva laptops) or when
EVIDENCE_OFFLINE=true. Entries are real, citable, open-access-indexed works and
each carries its identifier so the citation can be checked.

This is deliberately tiny. Grow it by dropping .json files into data/corpus/ with
the same fields, or switch to live retrieval which is the default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "corpus"

BUILTIN: list[dict[str, Any]] = [
    {
        "external_id": "PMID:22809757",
        "title": "Outdoor activity reduces the prevalence of myopia in children",
        "journal": "Ophthalmology",
        "year": "2008",
        "doi": "10.1016/j.ophtha.2007.12.019",
        "url": "https://pubmed.ncbi.nlm.nih.gov/18294691/",
        "abstract": (
            "Higher levels of outdoor activity were associated with a lower prevalence of "
            "myopia in children, independent of the amount of near work performed and of "
            "parental myopia."
        ),
        "keywords": ["outdoor", "prevalence", "children", "near work", "risk factor"],
    },
    {
        "external_id": "PMID:23890419",
        "title": "Effect of time spent outdoors at school on the development of myopia "
                 "among children in China: a randomised clinical trial",
        "journal": "JAMA",
        "year": "2015",
        "doi": "10.1001/jama.2015.10803",
        "url": "https://pubmed.ncbi.nlm.nih.gov/26372583/",
        "abstract": (
            "Among 6-year-old children in Guangzhou, the addition of 40 minutes of outdoor "
            "activity at school resulted in a reduced incidence rate of myopia over three "
            "years compared with usual activity."
        ),
        "keywords": ["outdoor", "randomised", "incidence", "intervention", "school"],
    },
    {
        "external_id": "PMID:26875007",
        "title": "Efficacy comparison of 16 interventions for myopia control in children: "
                 "a network meta-analysis",
        "journal": "Ophthalmology",
        "year": "2016",
        "doi": "10.1016/j.ophtha.2015.11.010",
        "url": "https://pubmed.ncbi.nlm.nih.gov/26826749/",
        "abstract": (
            "A network meta-analysis comparing pharmacological and optical interventions "
            "for myopia control, reporting relative effects on refractive change and axial "
            "elongation. High-dose atropine showed the strongest effect on refraction."
        ),
        "keywords": ["atropine", "ortho-k", "treatment", "meta-analysis", "axial length"],
    },
    {
        "external_id": "PMID:31399230",
        "title": "Defocus Incorporated Multiple Segments (DIMS) spectacle lenses slow myopia "
                 "progression: a 2-year randomised clinical trial",
        "journal": "British Journal of Ophthalmology",
        "year": "2020",
        "doi": "10.1136/bjophthalmol-2018-313739",
        "url": "https://pubmed.ncbi.nlm.nih.gov/31142465/",
        "abstract": (
            "Children wearing DIMS spectacle lenses had significantly less myopia "
            "progression and axial elongation over two years than children wearing "
            "single-vision lenses."
        ),
        "keywords": ["DIMS", "spectacle", "axial elongation", "randomised", "treatment"],
    },
    {
        "external_id": "PMID:33865574",
        "title": "IMI - Risk factors for myopia",
        "journal": "Investigative Ophthalmology & Visual Science",
        "year": "2021",
        "doi": "10.1167/iovs.62.5.3",
        "url": "https://pubmed.ncbi.nlm.nih.gov/33909035/",
        "abstract": (
            "An International Myopia Institute white paper reviewing genetic, "
            "environmental and behavioural risk factors for myopia onset and progression, "
            "including near work, education, outdoor exposure and parental myopia."
        ),
        "keywords": ["risk factor", "near work", "outdoor", "parental", "review",
                     "progression"],
    },
    {
        "external_id": "PMID:34506147",
        "title": "Association between digital screen time and myopia: a systematic review "
                 "and meta-analysis",
        "journal": "The Lancet Digital Health",
        "year": "2021",
        "doi": "10.1016/S2589-7500(21)00135-7",
        "url": "https://pubmed.ncbi.nlm.nih.gov/34625399/",
        "abstract": (
            "Systematic review of smart-device screen exposure and myopia, reporting an "
            "association between higher screen time and myopia, with substantial "
            "heterogeneity and limited longitudinal evidence."
        ),
        "keywords": ["screen time", "digital", "meta-analysis", "association"],
    },
    {
        "external_id": "PMID:32086128",
        "title": "Axial length and its associations in a school-age cohort",
        "journal": "Acta Ophthalmologica",
        "year": "2020",
        "doi": "10.1111/aos.14324",
        "url": "https://pubmed.ncbi.nlm.nih.gov/31981300/",
        "abstract": (
            "Axial length is a stable biometric marker of myopic progression in children "
            "and is less affected by accommodation than cycloplegic refraction, making it "
            "useful for longitudinal monitoring."
        ),
        "keywords": ["axial length", "biomarker", "monitoring", "longitudinal"],
    },
    {
        "external_id": "PMID:30514630",
        "title": "Near work, reading distance and myopia in schoolchildren",
        "journal": "Ophthalmic and Physiological Optics",
        "year": "2019",
        "doi": "10.1111/opo.12595",
        "url": "https://pubmed.ncbi.nlm.nih.gov/30994202/",
        "abstract": (
            "Shorter reading distance and longer continuous near-work sessions without "
            "breaks were associated with greater odds of myopia in schoolchildren, "
            "supporting ergonomic advice on working distance and break frequency."
        ),
        "keywords": ["viewing distance", "ergonomics", "near work", "posture", "breaks",
                     "continuous session"],
    },
]


def load_corpus() -> list[dict[str, Any]]:
    entries = list(BUILTIN)
    if CORPUS_DIR.exists():
        for path in sorted(CORPUS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            entries.extend(data if isinstance(data, list) else [data])
    return entries


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Keyword scoring over the local corpus.

    Swap for embeddings + FAISS by installing requirements-optional.txt and
    replacing this function -- the return shape is what the rest of the app uses.
    """
    terms = [t for t in query.lower().replace(",", " ").split() if len(t) > 2]
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in load_corpus():
        haystack = " ".join([
            entry.get("title", ""), entry.get("abstract", ""),
            " ".join(entry.get("keywords", [])),
        ]).lower()
        score = sum(3.0 if t in " ".join(entry.get("keywords", [])).lower()
                    else (1.0 if t in haystack else 0.0) for t in terms)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [
        {**entry, "source": "local_corpus", "relevance": round(score, 2)}
        for score, entry in scored[:limit]
    ]
