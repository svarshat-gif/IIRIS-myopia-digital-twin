"""The agent's tool belt.

Every tool is a plain Python function with a declared JSON schema. The agent can
ONLY obtain facts by calling these; it has no other access to data. That is what
makes the answer auditable: the trace records which tools ran with which
arguments, and the answer is composed from their outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Patient
from app.evidence import retriever
from app.explain import explainer
from app.ml import registry
from app.simulator import engine
from app.simulator.constraints import ScenarioRejected
from app.twin import service as twin_service


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    returns: str = ""
    tags: list[str] = field(default_factory=list)

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "returns": self.returns,
            "tags": self.tags,
        }


class ToolError(RuntimeError):
    pass


def _require_state(db: Session, patient_id: str) -> dict[str, Any]:
    patient = twin_service.get_patient(db, patient_id)
    if patient is None:
        raise ToolError(f"No patient with id '{patient_id}'.")
    version = twin_service.get_current_version(db, patient_id)
    if version is not None:
        return version.state_json
    try:
        return twin_service.build_state(db, patient)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

def t_list_patients(db: Session, limit: int = 20) -> dict[str, Any]:
    rows = db.scalars(select(Patient).limit(limit)).all()
    return {"patients": [
        {"patient_id": p.patient_id, "external_key": p.external_key,
         "age_at_start": p.age_at_start, "data_source": p.data_source}
        for p in rows
    ]}


def t_get_twin(db: Session, patient_id: str) -> dict[str, Any]:
    state = _require_state(db, patient_id)
    return {
        "patient_id": patient_id,
        "twin_version": state.get("version"),
        "current": state["current"],
        "derived": state["derived"],
        "data_completeness": state["data_completeness"],
        "n_visits": state["derived"]["n_visits"],
        "model_version": state.get("model_version"),
    }


def t_get_history(db: Session, patient_id: str, limit: int = 12) -> dict[str, Any]:
    state = _require_state(db, patient_id)
    history = state["history"][-limit:]
    return {"patient_id": patient_id, "n_visits": len(state["history"]),
            "visits": history}


def t_predict(db: Session, patient_id: str) -> dict[str, Any]:
    state = _require_state(db, patient_id)
    prediction = state.get("prediction")
    if not prediction:
        if not registry.is_ready():
            raise ToolError("No trained model is loaded, so no prediction can be made.")
        prediction = twin_service.predict_from_state(state["features"])
    return {"patient_id": patient_id, "prediction": prediction}


def t_simulate(db: Session, patient_id: str, changes: dict[str, Any],
               label: str | None = None) -> dict[str, Any]:
    state = _require_state(db, patient_id)
    try:
        return engine.simulate(state, {"changes": changes, "label": label})
    except ScenarioRejected as exc:
        raise ToolError(f"Scenario rejected as implausible: {'; '.join(exc.errors)}") from exc


def t_compare_scenarios(db: Session, patient_id: str,
                        scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    state = _require_state(db, patient_id)
    return engine.simulate_many(state, scenarios)


def t_sensitivity(db: Session, patient_id: str, input_name: str,
                  values: list[float], horizon: str = "12m") -> dict[str, Any]:
    state = _require_state(db, patient_id)
    return engine.sensitivity_sweep(state, input_name, values, horizon)


def t_explain(db: Session, patient_id: str, target: str = "se_12m") -> dict[str, Any]:
    state = _require_state(db, patient_id)
    if not registry.is_ready():
        raise ToolError("No trained model is loaded, so no explanation can be produced.")
    return explainer.explain_prediction(state["features"], target=target)


def t_retrieve_evidence(db: Session, query: str, limit: int = 4) -> dict[str, Any]:
    return retriever.retrieve(db, query, limit=limit)


def t_compare_versions(db: Session, patient_id: str, from_version: int,
                       to_version: int) -> dict[str, Any]:
    try:
        return twin_service.compare_versions(db, patient_id, from_version, to_version)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def t_flag_changes(db: Session, patient_id: str) -> dict[str, Any]:
    versions = twin_service.list_versions(db, patient_id)
    if len(versions) < 2:
        return {
            "patient_id": patient_id,
            "materially_changed": False,
            "flags": [],
            "note": "Only one twin version exists, so there is nothing to compare yet.",
        }
    return twin_service.compare_versions(
        db, patient_id, versions[-2].version, versions[-1].version)


def t_model_info(db: Session) -> dict[str, Any]:
    if not registry.is_ready():
        raise ToolError("No trained model bundle is loaded.")
    bundle = registry.load_bundle()
    m = bundle.get("metrics", {})
    return {
        "model_version": bundle["model_version"],
        "trained_at": bundle["trained_at"],
        "data_is_synthetic": bundle["data_is_synthetic"],
        "regression": {k: {"mae": v["mae"], "rmse": v["rmse"], "r2": v["r2"],
                           "interval_coverage": v.get("interval_coverage")}
                       for k, v in m.get("regression", {}).items()},
        "risk": m.get("risk", {}),
        "split": m.get("split", {}),
    }


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def _p(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


TOOLS: dict[str, Tool] = {
    t.name: t for t in [
        Tool("list_patients", "List patients available in this deployment.",
             _p({"limit": {"type": "integer", "default": 20}}, []),
             t_list_patients, "patient_id list", ["twin"]),
        Tool("get_twin",
             "Return the patient's current twin state: latest measurements, derived "
             "trend, data completeness and twin version.",
             _p({"patient_id": {"type": "string"}}, ["patient_id"]),
             t_get_twin, "twin state summary", ["twin"]),
        Tool("get_history", "Return the patient's recorded visit history.",
             _p({"patient_id": {"type": "string"},
                 "limit": {"type": "integer", "default": 12}}, ["patient_id"]),
             t_get_history, "list of visits", ["twin"]),
        Tool("predict",
             "Return the model's 6- and 12-month predictions for spherical equivalent "
             "and axial length, each with a prediction interval, plus progression risk.",
             _p({"patient_id": {"type": "string"}}, ["patient_id"]),
             t_predict, "predictions with uncertainty", ["prediction"]),
        Tool("simulate",
             "Run one what-if scenario: change behavioural/ergonomic inputs and compare "
             "the resulting predicted trajectory with the baseline.",
             _p({"patient_id": {"type": "string"},
                 "changes": {"type": "object",
                             "description": "e.g. {\"outdoor_min\": 120, "
                                            "\"screen_time_hours\": 3}"},
                 "label": {"type": "string"}}, ["patient_id", "changes"]),
             t_simulate, "baseline vs counterfactual comparison", ["simulation"]),
        Tool("compare_scenarios", "Run several what-if scenarios and return all of them.",
             _p({"patient_id": {"type": "string"},
                 "scenarios": {"type": "array", "items": {"type": "object"}}},
                ["patient_id", "scenarios"]),
             t_compare_scenarios, "list of scenario comparisons", ["simulation"]),
        Tool("sensitivity",
             "Sweep one modifiable input across a range of values and return the "
             "predicted outcome at each value (dose-response curve).",
             _p({"patient_id": {"type": "string"}, "input_name": {"type": "string"},
                 "values": {"type": "array", "items": {"type": "number"}},
                 "horizon": {"type": "string", "default": "12m"}},
                ["patient_id", "input_name", "values"]),
             t_sensitivity, "curve of predictions", ["simulation"]),
        Tool("explain",
             "Explain one prediction: which inputs pushed it up or down, with a plain "
             "language summary.",
             _p({"patient_id": {"type": "string"},
                 "target": {"type": "string", "default": "se_12m",
                            "enum": ["se_6m", "se_12m", "al_6m", "al_12m"]}},
                ["patient_id"]),
             t_explain, "attribution list", ["explanation"]),
        Tool("retrieve_evidence",
             "Search the published literature (Europe PMC / PubMed, or the bundled "
             "corpus offline) and return citations.",
             _p({"query": {"type": "string"},
                 "limit": {"type": "integer", "default": 4}}, ["query"]),
             t_retrieve_evidence, "citations", ["evidence"]),
        Tool("compare_versions",
             "Compare two stored twin versions and report what changed.",
             _p({"patient_id": {"type": "string"}, "from_version": {"type": "integer"},
                 "to_version": {"type": "integer"}},
                ["patient_id", "from_version", "to_version"]),
             t_compare_versions, "diff between versions", ["monitor"]),
        Tool("flag_changes",
             "Check whether the most recent update materially changed the patient's "
             "predicted trajectory or risk band.",
             _p({"patient_id": {"type": "string"}}, ["patient_id"]),
             t_flag_changes, "change flags", ["monitor"]),
        Tool("model_info",
             "Report the loaded model version, how it was validated and on what data.",
             _p({}, []), t_model_info, "model metadata and metrics", ["meta"]),
    ]
}


def tool_schemas() -> list[dict[str, Any]]:
    return [t.schema() for t in TOOLS.values()]


def call_tool(db: Session, name: str, args: dict[str, Any]) -> Any:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool '{name}'. Available: {sorted(TOOLS)}")
    return tool.fn(db, **args)
