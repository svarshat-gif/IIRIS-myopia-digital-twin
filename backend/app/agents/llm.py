"""Optional LLM layer.

The agent is fully functional WITHOUT any LLM. When one is configured it does
exactly one job: turn a structured facts payload into fluent prose. It is never
asked to compute, estimate, or recall a clinical value.

Guardrail (`verify_numbers`): every number in the generated text must already
appear in the facts the tools produced. If a number is not traceable, the
generated text is DISCARDED and the deterministic answer is returned instead.
That check runs on every LLM answer, so a hallucinated value cannot reach the UI.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You explain the output of a myopia Digital Twin to a clinician.

ABSOLUTE RULES:
1. Use ONLY the numbers and facts in the JSON provided. Never introduce a number
   that is not in that JSON. Never round differently or convert units.
2. Never state or imply that a behaviour change WILL cause a clinical outcome.
   Simulated results are model estimates of an association, not causal effects.
3. Never give a diagnosis, a prescription, or a treatment recommendation.
4. If the JSON does not contain what is needed to answer, say so plainly.
5. Always mention the uncertainty interval when you quote a predicted value.
6. Be concise: at most 6 sentences, plain clinical English, no bullet lists of
   technology names.
"""

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def is_enabled() -> bool:
    return settings.llm_provider.lower() not in {"", "none", "off", "disabled"}


def _collect_numbers(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        out.add(_norm(float(obj)))
    elif isinstance(obj, str):
        for m in NUMBER_RE.findall(obj):
            out.add(_norm(float(m)))


def _norm(x: float) -> str:
    return f"{round(x, 3):g}"


def verify_numbers(text: str, facts: Any) -> tuple[bool, list[str]]:
    """Every number in `text` must be derivable from `facts`.

    Percentages are allowed to match their 0-1 probability form (0.31 -> 31%),
    and a value quoted at lower precision than the source counts as a match.
    """
    allowed: set[str] = set()
    _collect_numbers(facts, allowed)
    # Percentage forms of any probability-like value.
    for value in list(allowed):
        try:
            f = float(value)
        except ValueError:
            continue
        if 0.0 <= abs(f) <= 1.0:
            allowed.add(_norm(f * 100))
    # Rounded forms, so "-2.4 D" matches a stored -2.42.
    for value in list(allowed):
        try:
            f = float(value)
        except ValueError:
            continue
        allowed.add(_norm(round(f, 2)))
        allowed.add(_norm(round(f, 1)))
        allowed.add(_norm(round(f)))

    unsupported = []
    for token in NUMBER_RE.findall(text):
        value = float(token)
        if _norm(value) in allowed:
            continue
        unsupported.append(token)
    return (not unsupported), unsupported


def _call_ollama(prompt: str) -> str:
    url = f"{settings.llm_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()


def narrate(question: str, facts: dict[str, Any],
            fallback: str) -> dict[str, Any]:
    """Return {answer, llm_used, guardrail}. Falls back on any failure."""
    if not is_enabled():
        return {"answer": fallback, "llm_used": "none",
                "guardrail": {"checked": False,
                              "reason": "No LLM configured; deterministic answer used."}}

    prompt = (
        f"Clinician question:\n{question}\n\n"
        f"Facts produced by the twin's tools (the ONLY permitted source):\n"
        f"{json.dumps(facts, indent=2, default=str)[:12000]}\n\n"
        f"Write the answer now, following the rules."
    )
    provider = settings.llm_provider.lower()
    try:
        if provider != "ollama":
            raise ValueError("Only a local Ollama model is supported")
        from urllib.parse import urlparse
        if urlparse(settings.llm_base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Ollama must use loopback")
        text = _call_ollama(prompt)
    except Exception as exc:
        log.warning("LLM call failed (%s): %s", provider, exc)
        return {"answer": fallback, "llm_used": "none",
                "guardrail": {"checked": False,
                              "reason": f"LLM unavailable ({type(exc).__name__}); "
                                        f"deterministic answer used."}}

    if not text:
        return {"answer": fallback, "llm_used": "none",
                "guardrail": {"checked": False, "reason": "Empty LLM response."}}

    ok, unsupported = verify_numbers(text, facts)
    if not ok:
        log.warning("LLM answer rejected; unsupported numbers: %s", unsupported)
        return {
            "answer": fallback,
            "llm_used": f"{provider}:{settings.llm_model} (rejected)",
            "guardrail": {
                "checked": True, "passed": False, "unsupported_numbers": unsupported,
                "reason": "The generated answer contained numbers that did not come "
                          "from the tools, so it was discarded and the deterministic "
                          "answer was returned instead.",
            },
        }

    return {
        "answer": text,
        "llm_used": f"{provider}:{settings.llm_model}",
        "guardrail": {"checked": True, "passed": True,
                      "reason": "Every number in the answer was traced back to tool output."},
    }
