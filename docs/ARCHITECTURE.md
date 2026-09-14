# Architecture

How the pieces fit, and where to extend each one.

---

## The central idea

A static ML model maps one input table to one prediction. A **digital twin** maintains a
persistent representation of one patient — current state, history, predicted future state,
and what-if states — and *updates* when a new observation arrives instead of starting from
zero.

Concretely, that means three things this codebase does that a `/predict` service does not:

1. **State is stored and versioned.** Every update writes a new immutable snapshot. Old
   snapshots are never mutated, so any past state can be replayed exactly.
2. **Prediction is derived from history, not just the latest row.** Trend slopes, deltas
   since baseline, rolling exposure averages and time-since-last-visit are all features.
3. **The same state can be forked.** The simulator clones the twin, changes selected inputs,
   and runs the identical feature builder and model — which is what makes a counterfactual
   comparable to its baseline.

---

## Request flow: adding an observation

```
POST /api/v1/patients/{id}/observations
        │
        ├─ pydantic validation      impossible values -> 422
        ├─ duplicate visit check    same date -> 409
        ├─ store Observation row
        │
        ├─ twin_service.refresh_twin()
        │       ├─ load ALL observations for this patient, ordered
        │       ├─ build_feature_row(history)        <- the shared builder
        │       ├─ registry.predict_from_row()       <- median + conformal interval + risk
        │       ├─ assemble state (current, history, derived, completeness, provenance)
        │       └─ save_version()  -> TwinVersion(version = max + 1)  + Prediction rows
        │
        ├─ compare_versions(previous, new)  -> observed + predicted deltas, material flags
        └─ 201 { twin_version, previous_version, twin, change_summary }
```

The response is deliberately rich: the UI can show the version bump, the recomputed
predictions and what materially changed, without a second round trip.

---

## The feature builder is the load-bearing component

[`app/ml/features.py:build_feature_row`](../backend/app/ml/features.py) is used by:

- **training** (`app/ml/dataset.py`, once per patient-visit over the history so far)
- **live prediction** (`app/twin/service.py`)
- **the simulator** (`app/simulator/engine.py`, with `overrides`)

If these ever diverge, counterfactual results become meaningless — the scenario would be
scored by a different transformation than the baseline. That is why there is exactly one
implementation and why `overrides` is a parameter of the builder rather than a mutation
performed by the caller.

`overrides` applies to the **current visit only**. History is preserved, so a scenario that
raises outdoor time changes `outdoor_min` to the new value but moves `outdoor_mean_3`
only partly — which is correct: you cannot retroactively change last year's behaviour.
This is asserted in `tests/test_units.py::test_overrides_only_affect_the_current_visit`.

### Feature groups

`CLINICAL_FEATURES` / `BEHAVIOUR_FEATURES` / `ERGONOMIC_FEATURES` exist so the ablation
study can train on nested subsets with identical splits and hyperparameters. Adding a
feature means adding it to exactly one group; the ablation picks it up automatically.

---

## Uncertainty

Three models per target:

| Model | Loss | Purpose |
|---|---|---|
| median | squared error | the point estimate |
| lower | quantile, q=0.05 | interval floor |
| upper | quantile, q=0.95 | interval ceiling |

Quantile forests routinely under-cover. Measured here: **0.72–0.77** against a nominal 0.90.

So a **split-conformal correction** (Romano et al., *Conformalized Quantile Regression*) is
fitted on a validation split of **patients the models never saw**:

```
score_i = max(lower(x_i) - y_i,  y_i - upper(x_i))     # how far outside the band
delta   = ceil((n+1)·0.90)/n  quantile of the scores
interval = [lower - delta,  upper + delta]
```

Measured coverage after calibration: **0.91–0.93**. `delta` is stored in the bundle and
applied in `registry.predict_from_row`, so every consumer gets calibrated intervals with no
extra step. The model card reports raw and calibrated coverage side by side.

---

## The simulator

```
current twin state X(t)  +  requested changes E
        │
        ├─ constraints.validate_scenario(E, current)
        │       HARD violation  -> ScenarioRejected -> HTTP 422
        │       SOFT violation  -> accepted, warning attached to the response
        │
        ├─ baseline      = model( build_feature_row(history) )
        ├─ counterfactual = model( build_feature_row(history, overrides=E) )
        │
        └─ compare: per-horizon deltas, direction, whether the difference is
                    smaller than the prediction interval, which model inputs moved
```

Two properties worth pointing out in a review:

- **Rejection, not extrapolation.** `outdoor_min: 5000` returns `422` with a reason instead
  of a confident-looking number.
- **Difference vs uncertainty.** `smaller_than_uncertainty` is computed per outcome, and the
  UI renders "not a meaningful separation" rather than letting a 0.02 D shift read as a result.

`sensitivity_sweep` runs the same machinery across a range of one input to produce the
dose-response curve.

---

## The agent

```
question -> [route] -> [plan] -> [execute] -> [check] -> [compose] -> answer
```

| Node | Job |
|---|---|
| `route` | Classify intent. A conditional clause plus a modifiable input ⇒ `simulate`, checked before the keyword lists. |
| `plan` | Choose tools and record *why* each one is being called. |
| `execute` | Call the tools, record status/args/errors in a trace. Tool failure degrades the answer; it never 500s. |
| `check` | If no tool produced facts, record that instead of answering from nothing. |
| `compose` | Build the answer from tool output. Optionally hand facts to an LLM to phrase. |

**Tools are the only source of facts.** `app/agents/tools.py` declares each one with a JSON
schema; `GET /api/v1/agent/tools` publishes them. `GET /api/v1/agent/graph` introspects the
graph from the running code, so the diagram in a report cannot drift from the implementation.

### The LLM guardrail

If an LLM is attached, it receives a facts payload and a system prompt forbidding new
numbers. Its output then passes `verify_numbers`: every numeric token in the text must trace
back to the facts (allowing rounding, percentage forms, and small integers used as ordinals).
On failure the generated text is **discarded** and the deterministic answer is returned, with
`guardrail.passed = false` and the offending tokens listed in the response.

This is why the demo cannot be broken by a hallucinating small model, and why the agent works
identically with `LLM_PROVIDER=none`.

---

## Data model

| Table | Role |
|---|---|
| `patients` | De-identified subject. No name, MRN or contact fields exist in the schema. |
| `observations` | One visit: clinical + behaviour + ergonomics, all nullable except SE/AL |
| `twin_versions` | **Immutable snapshots.** `state_json` holds the whole twin at that moment. |
| `predictions` | Per version, per horizon, with bounds and model version |
| `simulations` | Scenario + results, tied to the baseline twin version |
| `evidence` | Retrieved citations, cached with a timestamp |
| `agent_runs` | Audit trail: question, plan, full tool trace, answer, LLM used |

`twin_versions` is the table that makes the project defensible. When someone asks *"what did
your system know before the latest measurement?"*, the answer is a stored row, not a
recomputation.

---

## Extension points

| To add… | Change | Nothing else breaks because… |
|---|---|---|
| A new predictor | Add to a feature group in `features.py` and populate it in `build_feature_row` | Training, prediction and simulation all read the same list |
| A new horizon | `HORIZONS` in `dataset.py`, retrain | The registry iterates `bundle["horizons"]` |
| A new modifiable input | `MODIFIABLE_INPUTS` + `MAX_PLAUSIBLE_DELTA` | The UI builds sliders from `GET /meta/inputs` |
| A new agent capability | Add a `Tool` to `TOOLS` and a plan step | The trace, audit log and schema endpoint pick it up automatically |
| A different model family | `train_regressors` in `train.py` | The registry only needs `.predict` / `.predict_proba` |
| Semantic RAG | Replace `corpus.search()` | Callers depend on the return shape only |
| LangGraph | Wrap the same `NODES` in a `StateGraph` | Node functions are the single source of truth |
