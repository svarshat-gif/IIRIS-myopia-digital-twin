"""The agent graph.

    question -> [router] -> [plan] -> [execute tools] -> [check] -> [compose] -> answer

Written as an explicit node/edge graph rather than a prompt chain, for three
reasons that matter for the project:

  * It is auditable. Every answer stores the plan and the full tool trace.
  * It works with no LLM at all. The router is rule-based, so the demo cannot
    fail because a model server is down.
  * It maps 1:1 onto LangGraph. `app/agents/langgraph_runtime.py` runs the same
    nodes under LangGraph when that package is installed; the node functions here
    are the single source of truth.

The LLM (if any) is only invoked in `compose`, and only to phrase facts that the
tools already produced.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agents import llm
from app.agents.tools import ToolError, call_tool
from app.core.config import settings
from app.evidence.retriever import evidence_query_for

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Intent routing
# --------------------------------------------------------------------------

INTENTS: list[tuple[str, list[str]]] = [
    ("simulate", ["what if", "what-if", "if the patient", "scenario", "increase",
                  "decrease", "reduce", "more outdoor", "less screen", "instead of",
                  "suppose", "counterfactual", "would happen", "spent more",
                  "spent less", "cut down", "further away", "closer"]),
    ("explain", ["why", "explain", "which factor", "what is driving", "reason",
                 "contributed", "shap", "attribution", "because"]),
    ("monitor", ["change", "changed", "since last", "new visit", "compare version",
                 "different from before", "worse", "better than last", "flag"]),
    ("evidence", ["evidence", "literature", "paper", "study", "studies", "research",
                  "citation", "published", "guideline"]),
    ("model", ["how accurate", "model version", "how good", "validated", "performance",
               "trained", "mae", "auc", "metrics"]),
    ("predict", ["predict", "prediction", "forecast", "trajectory", "next year",
                 "12 month", "6 month", "risk", "progress", "future", "outlook"]),
    ("twin", ["current", "state", "summary", "status", "history", "visits",
              "measurement", "who is", "overview"]),
]

# Phrases in the question -> which modifiable input they refer to.
INPUT_PATTERNS: dict[str, list[str]] = {
    "outdoor_min": ["outdoor", "outside", "sunlight", "playing out", "daylight"],
    "screen_time_hours": ["screen", "device", "phone", "tablet", "tv"],
    "near_work_min": ["near work", "nearwork", "reading", "homework", "study time",
                      "studying"],
    "viewing_distance_cm": ["distance", "further away", "closer", "arm's length",
                            "viewing distance", "holds"],
    "posture_score": ["posture", "slouch", "sitting"],
    "continuous_session_min": ["break", "session", "continuous", "without stopping",
                               "at a stretch"],
    "sleep_hours": ["sleep", "bedtime", "rest"],
}

# Default counterfactual value when the user asks for a direction but no number,
# e.g. "what if they went outside more?". Chosen as a commonly studied level, and
# always reported back to the user as an assumption.
DIRECTIONAL_DEFAULTS: dict[str, dict[str, float]] = {
    "outdoor_min": {"more": 120.0, "less": 20.0},
    "screen_time_hours": {"more": 8.0, "less": 2.0},
    "near_work_min": {"more": 360.0, "less": 120.0},
    "viewing_distance_cm": {"more": 45.0, "less": 20.0},
    "posture_score": {"more": 0.9, "less": 0.4},
    "continuous_session_min": {"more": 120.0, "less": 20.0},
    "sleep_hours": {"more": 9.5, "less": 6.0},
}

INCREASE_WORDS = ["increase", "more", "raise", "longer", "higher", "further", "extra",
                  "double", "up to", "improve"]
DECREASE_WORDS = ["decrease", "less", "reduce", "shorter", "lower", "cut", "closer",
                  "drop", "down to", "halve"]


@dataclass
class AgentState:
    """Passed between nodes. This is the LangGraph state object when that runtime is used."""

    question: str
    patient_id: str | None
    db: Session
    intent: str = "twin"
    plan: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    answer: str = ""
    llm_used: str = "none"
    guardrail: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Node: route
# --------------------------------------------------------------------------

# A conditional clause plus a mention of something the patient can actually change
# is a what-if question, however it is phrased ("what happens to the trajectory IF
# this child spends 2 hours OUTDOORS?"). This is checked before the keyword lists,
# which would otherwise route it to plain prediction on the word "trajectory".
CONDITIONAL_MARKERS = [" if ", "if the", "if they", "if we", "if this", "suppose",
                       "were to", "instead of", "assuming", "hypothetically",
                       "what would", "how would"]


def _mentions_modifiable_input(q: str) -> bool:
    return any(p in q for phrases in INPUT_PATTERNS.values() for p in phrases)


def node_route(state: AgentState) -> AgentState:
    q = f" {state.question.lower()} "
    if (any(m in q for m in CONDITIONAL_MARKERS) and _mentions_modifiable_input(q)):
        state.intent = "simulate"
        return state
    for intent, keywords in INTENTS:
        if any(k in q for k in keywords):
            state.intent = intent
            return state
    state.intent = "twin"
    return state


def _extract_changes(question: str, current: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Pull scenario values out of natural language.

    Explicit numbers win ("2 hours of screen time"). Otherwise a direction word
    maps to a documented default, and the assumption is reported to the user.
    """
    q = question.lower()
    changes: dict[str, Any] = {}
    assumptions: list[str] = []

    for input_name, phrases in INPUT_PATTERNS.items():
        hit = next((p for p in phrases if p in q), None)
        if hit is None:
            continue

        # Look for a number near the matched phrase.
        idx = q.find(hit)
        window = q[max(0, idx - 45): idx + 45]
        numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", window)]
        value: float | None = None
        if numbers:
            value = numbers[0]
            if input_name == "outdoor_min" and ("hour" in window or "hr" in window):
                value *= 60.0
            if input_name == "near_work_min" and ("hour" in window or "hr" in window):
                value *= 60.0
            if input_name == "screen_time_hours" and ("minute" in window or "min" in window):
                value /= 60.0

        if value is None:
            direction = ("more" if any(w in window or w in q for w in INCREASE_WORDS)
                         else "less" if any(w in window or w in q for w in DECREASE_WORDS)
                         else None)
            if direction is None:
                continue
            value = DIRECTIONAL_DEFAULTS[input_name][direction]
            baseline = current.get(input_name)
            assumptions.append(
                f"The question asked for '{direction}' {input_name.replace('_', ' ')} "
                f"without a number, so the scenario used {value:g} "
                f"(current value: {baseline if baseline is not None else 'not recorded'})."
            )
        changes[input_name] = value

    return changes, assumptions


# --------------------------------------------------------------------------
# Node: plan
# --------------------------------------------------------------------------

def node_plan(state: AgentState) -> AgentState:
    pid = state.patient_id
    plan: list[dict[str, Any]] = []

    if state.intent == "model":
        state.plan = [{"tool": "model_info", "args": {}, "why": "Report how the model was built and validated."}]
        return state

    if pid is None:
        state.plan = [{"tool": "list_patients", "args": {},
                       "why": "No patient was specified, so list what is available."}]
        return state

    plan.append({"tool": "get_twin", "args": {"patient_id": pid},
                 "why": "Every answer starts from the patient's current twin state."})

    if state.intent in {"predict", "simulate", "explain", "twin", "monitor"}:
        plan.append({"tool": "predict", "args": {"patient_id": pid},
                     "why": "Get the baseline predicted trajectory with uncertainty."})

    if state.intent == "simulate":
        plan.append({"tool": "__simulate_placeholder__", "args": {"patient_id": pid},
                     "why": "Run the requested what-if scenario against the twin."})

    if state.intent == "explain":
        plan.append({"tool": "explain", "args": {"patient_id": pid, "target": "se_12m"},
                     "why": "Attribute the 12-month prediction to individual inputs."})

    if state.intent == "monitor":
        plan.append({"tool": "flag_changes", "args": {"patient_id": pid},
                     "why": "Check whether the latest update moved the trajectory materially."})

    if state.intent == "twin":
        plan.append({"tool": "get_history", "args": {"patient_id": pid, "limit": 8},
                     "why": "Summarise the recorded visit history."})

    if state.intent in {"evidence", "simulate"}:
        plan.append({"tool": "__evidence_placeholder__", "args": {},
                     "why": "Retrieve published literature relevant to the factors discussed."})

    state.plan = plan
    return state


# --------------------------------------------------------------------------
# Node: execute
# --------------------------------------------------------------------------

def node_execute(state: AgentState) -> AgentState:
    current_inputs: dict[str, Any] = {}
    assumptions: list[str] = []

    for step in state.plan:
        tool, args = step["tool"], dict(step["args"])

        if tool == "__simulate_placeholder__":
            changes, assumptions = _extract_changes(state.question, current_inputs)
            if not changes:
                state.issues.append(
                    "The question asked for a what-if scenario, but no modifiable input "
                    "could be identified. Ask about outdoor time, screen time, near work, "
                    "viewing distance, posture, session length or sleep."
                )
                state.trace.append({"tool": "simulate", "args": {}, "status": "skipped",
                                    "why": step["why"],
                                    "error": "no modifiable input found in the question"})
                continue
            tool, args = "simulate", {"patient_id": state.patient_id,
                                      "changes": changes,
                                      "label": "Agent scenario"}

        if tool == "__evidence_placeholder__":
            hints = list(state.facts.get("simulate", {}).get("applied_changes", []))
            hint_keys = [h["input"] for h in hints] if hints else _question_hints(state.question)
            tool, args = "retrieve_evidence", {
                "query": evidence_query_for(hint_keys), "limit": 3}

        try:
            result = call_tool(state.db, tool, args)
            state.facts[tool] = result
            state.trace.append({"tool": tool, "args": args, "status": "ok",
                                "why": step["why"]})
            if tool == "get_twin":
                current_inputs = {**(result["current"].get("behaviour") or {}),
                                  **(result["current"].get("ergonomics") or {}),
                                  "treatment": result["current"].get("treatment")}
        except ToolError as exc:
            state.issues.append(str(exc))
            state.trace.append({"tool": tool, "args": args, "status": "error",
                                "why": step["why"], "error": str(exc)})
        except Exception as exc:  # defensive: a tool bug must not 500 the agent
            state.issues.append(f"{tool} failed: {type(exc).__name__}: {exc}")
            state.trace.append({"tool": tool, "args": args, "status": "error",
                                "why": step["why"], "error": str(exc)})

    if assumptions:
        state.facts["assumptions"] = assumptions
    return state


def _question_hints(question: str) -> list[str]:
    q = question.lower()
    return [name for name, phrases in INPUT_PATTERNS.items()
            if any(p in q for p in phrases)] or ["axial_length"]


# --------------------------------------------------------------------------
# Node: check
# --------------------------------------------------------------------------

def node_check(state: AgentState) -> AgentState:
    """Refuse to answer from nothing. If no tool produced usable facts, say so."""
    ok_steps = [t for t in state.trace if t["status"] == "ok"]
    if not ok_steps:
        state.issues.insert(0, "No tool returned usable data for this question.")
    if state.intent == "simulate" and "simulate" not in state.facts:
        state.issues.append("No counterfactual result is available, so no what-if "
                            "comparison is reported below.")
    return state


# --------------------------------------------------------------------------
# Node: compose
# --------------------------------------------------------------------------

def _fmt(value: Any, digits: int = 2, unit: str = "") -> str:
    if value is None:
        return "not recorded"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}{unit}"
    return str(value)


def _deterministic_answer(state: AgentState) -> str:
    """Compose the answer from tool output alone. This is what ships when there
    is no LLM, and it is the fallback whenever the LLM guardrail trips."""
    parts: list[str] = []
    f = state.facts

    if "list_patients" in f:
        ids = [p["patient_id"] for p in f["list_patients"]["patients"]]
        return ("No patient was specified. Available patient ids: "
                + (", ".join(ids[:10]) if ids else "none loaded yet."))

    if "model_info" in f:
        mi = f["model_info"]
        reg = mi.get("regression", {})
        line = ", ".join(f"{k}: MAE {v['mae']}" for k, v in list(reg.items())[:4])
        parts.append(
            f"Model {mi['model_version']} (trained {mi['trained_at'][:10]}). "
            f"Held-out patient-level performance -- {line}."
        )
        if mi.get("risk"):
            parts.append(f"Progression-risk classifier ROC-AUC {mi['risk'].get('roc_auc')}, "
                         f"PR-AUC {mi['risk'].get('pr_auc')}.")
        if mi.get("data_is_synthetic"):
            parts.append("These figures come from SYNTHETIC data and are not clinical "
                         "performance results.")
        return " ".join(parts)

    twin = f.get("get_twin")
    if twin:
        cur = twin["current"]
        parts.append(
            f"Twin v{twin.get('twin_version')} for patient {twin['patient_id']}: at the "
            f"visit on {cur['visit_date']} the spherical equivalent was "
            f"{_fmt(cur['spherical_equivalent'], 2, ' D')} and the axial length "
            f"{_fmt(cur['axial_length'], 2, ' mm')}, across {twin['n_visits']} recorded "
            f"visits. Recent trend: {_fmt(twin['derived'].get('se_slope_per_year'), 2, ' D/year')} "
            f"and {_fmt(twin['derived'].get('al_slope_per_year'), 3, ' mm/year')}."
        )

    pred = (f.get("predict") or {}).get("prediction")
    if pred:
        h12 = pred["horizons"].get("12m", {})
        se, al = h12.get("se"), h12.get("al")
        if se:
            parts.append(
                f"At 12 months the model predicts SE {se['value']} D "
                f"(90% interval {se['lower']} to {se['upper']} D)"
                + (f" and axial length {al['value']} mm "
                   f"({al['lower']} to {al['upper']} mm)." if al else ".")
            )
        risk = pred.get("risk")
        if risk:
            parts.append(
                f"Estimated probability of fast progression is {risk['probability']:.2f} "
                f"({risk['band']} band). Definition: {risk['definition']}."
            )

    sim = f.get("simulate")
    if sim:
        applied = ", ".join(
            f"{c['label']} {_fmt(c['from'], 1)} -> {_fmt(c['to'], 1)}{c['unit']}"
            for c in sim["applied_changes"])
        parts.append(f"Scenario applied: {applied}.")
        cmp12 = sim["comparison"].get("12m", {})
        se = cmp12.get("se")
        if se:
            note = (" That difference is smaller than the model's own uncertainty, "
                    "so it should not be read as a meaningful separation."
                    if se["smaller_than_uncertainty"] else "")
            parts.append(
                f"Under this scenario the 12-month SE estimate moves from "
                f"{se['baseline']} D to {se['scenario']} D, a difference of "
                f"{se['difference']:+.2f} D.{note}"
            )
        al = cmp12.get("al")
        if al:
            parts.append(
                f"Predicted 12-month axial length moves from {al['baseline']} mm to "
                f"{al['scenario']} mm ({al['difference']:+.3f} mm).")
        risk = sim["comparison"].get("risk")
        if risk:
            parts.append(
                f"Estimated progression risk moves from {risk['baseline']:.2f} to "
                f"{risk['scenario']:.2f}.")
        for w in sim.get("warnings", []):
            parts.append(f"Caution: {w}")
        parts.append(sim["causal_disclaimer"])

    exp = f.get("explain")
    if exp:
        parts.append(f"Main drivers of the {exp['target_label'].lower()} "
                     f"({exp['method']}): " + " ".join(exp["plain_language"][:3]))
        parts.append(exp["attribution_disclaimer"])

    flags = f.get("flag_changes")
    if flags:
        if flags.get("materially_changed"):
            parts.append("Monitor flag: " + "; ".join(flags["flags"]) + ".")
        else:
            parts.append("Monitor: the latest update did not move the predicted "
                         "trajectory past the alert thresholds."
                         + (f" {flags['note']}" if flags.get("note") else ""))

    ev = f.get("retrieve_evidence")
    if ev and ev.get("results"):
        cites = "; ".join(
            f"{r['title']} ({r.get('journal') or 'n/a'}, {r.get('year') or 'n/a'}"
            f"{', ' + r['external_id'] if r.get('external_id') else ''})"
            for r in ev["results"][:3])
        parts.append(f"Related literature from {ev['source_used']}: {cites}.")
        parts.append(ev["caveat"])

    for a in f.get("assumptions", []):
        parts.append(f"Assumption: {a}")
    for issue in state.issues:
        parts.append(f"Note: {issue}")

    if not parts:
        return ("The tools did not return enough information to answer that. "
                "Try asking about the patient's current state, prediction, a what-if "
                "scenario, or the evidence behind a factor.")
    return " ".join(parts)


def node_compose(state: AgentState) -> AgentState:
    deterministic = _deterministic_answer(state)
    result = llm.narrate(state.question, state.facts, deterministic)
    state.answer = result["answer"]
    state.llm_used = result["llm_used"]
    state.guardrail = result["guardrail"]
    state.facts["deterministic_answer"] = deterministic
    return state


# --------------------------------------------------------------------------
# Graph definition + runner
# --------------------------------------------------------------------------

NODES = {
    "route": node_route,
    "plan": node_plan,
    "execute": node_execute,
    "check": node_check,
    "compose": node_compose,
}

EDGES = [("route", "plan"), ("plan", "execute"), ("execute", "check"),
         ("check", "compose"), ("compose", "END")]

ENTRY = "route"


def graph_spec() -> dict[str, Any]:
    """Introspection for the UI / report: the graph, drawn from the real code."""
    return {
        "entry": ENTRY,
        "nodes": [
            {"name": "route", "role": "Classify the question into an intent."},
            {"name": "plan", "role": "Choose which tools to call, and why."},
            {"name": "execute", "role": "Call the tools and record a trace."},
            {"name": "check", "role": "Verify that facts were actually produced."},
            {"name": "compose", "role": "Write the answer from tool output only."},
        ],
        "edges": [{"from": a, "to": b} for a, b in EDGES],
        "intents": [i for i, _ in INTENTS],
        "runtime": "langgraph" if _langgraph_available() else "builtin",
    }


def _langgraph_available() -> bool:
    from app.agents import langgraph_runtime  # noqa: PLC0415
    return langgraph_runtime.is_available()


def run(db: Session, question: str, patient_id: str | None) -> dict[str, Any]:
    """Execute the graph.

    LangGraph runs it when installed; otherwise the built-in loop walks the same
    nodes and edges. Either way the result is identical, so the demo cannot fail
    because a dependency is missing.
    """
    from app.agents import langgraph_runtime  # noqa: PLC0415

    runtime = "builtin"
    state = None
    if langgraph_runtime.is_available():
        try:
            state = langgraph_runtime.run(db, question, patient_id)
            runtime = "langgraph"
        except Exception as exc:      # never let the executor break the answer
            log.warning("LangGraph execution failed, using the built-in loop: %s", exc)
            state = None

    if state is None:
        state = AgentState(question=question, patient_id=patient_id, db=db)
        node = ENTRY
        while node != "END":
            state = NODES[node](state)
            node = next(b for a, b in EDGES if a == node)

    return {
        "question": question,
        "patient_id": patient_id,
        "intent": state.intent,
        "plan": [{k: v for k, v in step.items()} for step in state.plan],
        "trace": state.trace,
        "tools_called": [t["tool"] for t in state.trace if t["status"] == "ok"],
        "answer": state.answer,
        "deterministic_answer": state.facts.get("deterministic_answer"),
        "facts": {k: v for k, v in state.facts.items() if k != "deterministic_answer"},
        "issues": state.issues,
        "llm_used": state.llm_used,
        "guardrail": state.guardrail,
        "graph": {**graph_spec(), "runtime": runtime},
        "disclaimer": settings.disclaimer,
    }
