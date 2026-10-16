# Eight-step research demo (guide section 14)

Use only the included de-identified open DIMS records. Bootstrap seeds visits
through month 24 so the published month-36 visit can demonstrate an update.
Sign in as an administrator or an assigned clinician; no default password exists.

1. Open patient dims:D1. Show current SE/AL, missing habits/ergonomics, source,
   model version and the current twin version. Calendar dates are unknown; the
   displayed timeline is months since baseline.
2. Show the measured trajectory and prediction band. Explain that it is a tiny
   20-subject exploratory model with only two independent test subjects.
3. Show the attribution table. If SHAP is not installed, call it feature ablation,
   not an exact Shapley value. Attribution explains this model, not causation.
4. Check scenario availability. Outdoor-time and viewing-distance effects are
   explicitly unavailable because no training exposure data exist. This refusal
   is the correct result; do not manufacture two different futures.
5. Ask the agent "What changed since the last visit?" Show get_twin, predict and
   flag_changes in its trace. It works with LLM_PROVIDER=none.
6. Ask for published evidence. Show PMID/DOI source IDs and the offline fallback
   when EVIDENCE_OFFLINE=true. These papers do not validate an individual forecast.
7. Add the actual D1 month-36 observation from the source workbook: SE -5.13 D,
   AL 26.89 mm, followup_month 36. Leave other fields missing. The POST response
   increments the version, recalculates prediction and persists a monitor result.
   Show the current flag, compare the last versions and replay the preceding one.
8. End on the model card. Change forecasts beat carry-forward on the existing
   two-patient benchmark; SE still trails Ridge/RF. Neither R-squared nor coverage
   establishes 95% prediction accuracy. Show onset accuracy alongside its low
   sensitivity and 87.1% majority baseline. Observational estimates are not
   diagnosis, prescribing, causal effects or clinical validation.

Do not add invented visits, habits, appointments or names to a public demo. The
D1 row above is a published observation, not a suggested future result. To repeat
step 7, use a fresh local demo DB or another genuinely withheld published visit;
never delete a real clinical history to reset a presentation.

After replacing a model, run `python scripts/refresh_model_predictions.py` from
backend to append current-model snapshots. Earlier versions remain immutable.
The supplied local demo was refreshed once; its version number may exceed the
number of observations because a model refresh is a separate event.
