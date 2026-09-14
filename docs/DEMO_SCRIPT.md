# The demo

5–7 minutes. The goal is not to show technology; it is to show a **capability that a static
model cannot provide**. Open with the clinical problem, then the new capability, then the
engineering — in that order.

**Setup:** `make demo`, then `make api` and `make ui` in two terminals. Have
<http://localhost:5173> and <http://localhost:8000/docs> open in two tabs.

---

## 30-second opening

> "Today, myopia is a sequence of separate clinic visits — a prescription here, an axial
> length measurement there. Our project turns those scattered measurements into a living,
> patient-specific computational twin. The twin remembers the patient's past, estimates the
> current trajectory, predicts what may happen next, and lets us test model-based what-if
> scenarios such as changes in outdoor exposure or viewing distance. Every result carries an
> explanation and an uncertainty range, and the whole twin is exposed through our own API,
> so when the next observation arrives the twin updates instead of starting from zero."

Then the novelty, before anyone asks:

> "The novelty is not that we trained one more classifier. It is the stateful, longitudinal
> twin: history → updated state → prediction with uncertainty → counterfactual scenario →
> explanation → evidence → API → next update. We are also testing whether behavioural and
> ergonomic information adds predictive value over clinical biomarkers alone."

---

## The walkthrough

### 1 · Open a patient — *Twin overview* (45 s)

Pick a patient with a `high risk` chip.

Point at: current SE and AL, recent trend in D/year, twin version, model version, and the
**data completeness bars**.

> "This is twin version 8. Behaviour data is 88% complete and ergonomics 100% — and where a
> field was not collected we leave it missing rather than filling it with a guess. The model
> handles missing inputs natively."

### 2 · The trajectory chart (45 s)

> "Observed history in dark, the model's forecast dashed, and the shaded band is a 90%
> prediction interval. That band is not decoration — it is conformally calibrated on
> patients the model never saw, so 90% really does mean about 90%. Raw quantile regression
> was covering only 72%, which would have made this system look far more confident than it is."

### 3 · Explain the prediction — *Explanation* tab (45 s)

> "For any individual prediction we can show which inputs pushed it up or down, with a plain
> language summary. Note the caption: this explains the *model*, not the disease. Attribution
> is not causation."

### 4 · Run a what-if — *What-if simulator* (90 s) ⭐

Click **"More outdoor time"**.

> "The simulator clones the twin, changes just that input, rebuilds the features with the
> same builder used in training, and re-runs the same model. Baseline in blue, scenario in
> green, on both spherical equivalent and axial length."

Point at the **Reading** column:

> "And where the estimated difference is smaller than the model's own prediction interval,
> we say so explicitly. We are not going to let a 0.02 dioptre difference look like a finding."

Then drag a slider to an extreme and hit **Run scenario**:

> "If you ask something implausible, it is rejected — not answered. That was a design
> requirement: a system that produces a confident-looking number for an impossible input is
> worse than one that refuses."

If time allows, run a **dose-response sweep** on outdoor time.

### 5 · Ask the agent — *Agent* tab (75 s) ⭐

Ask: *"How does the predicted trajectory change if this child spends 2 hours outdoors a day?"*

Then **click "Show tool trace"**. This is the part that matters.

> "It routed the question to a simulation intent, then called four tools: `get_twin`,
> `predict`, `simulate` and `retrieve_evidence` — each with a recorded reason. It is not
> paraphrasing a model output; it is planning and executing a task. And there is no LLM
> attached here at all. The answer is composed from tool output."

If asked about LLMs:

> "You can attach a local Ollama model to phrase the answer more fluently. When you do, every
> number in the generated text is checked against the tool output, and if a number cannot be
> traced the generated text is discarded and this deterministic answer is used instead. The
> model is not permitted to invent a clinical value."

### 6 · Evidence — *Evidence* tab (30 s)

> "Retrieval goes to Europe PMC first, PubMed second, and a bundled corpus offline, so the
> demo works without a network. Every citation carries its identifier. Note the caveat: this
> is background literature about myopia in general, not evidence about this patient."

### 7 · Add a new visit — *Add visit* tab (60 s) ⭐⭐

**This is the moment. Do not rush it.**

Enter a slightly worse SE and AL, and reduced outdoor time. Submit.

> "That was a POST to our own API. Watch the version chip: v8 → v9. The twin rebuilt, the
> predictions recomputed, and it is telling us whether this visit *materially* changed the
> outlook against defined thresholds."

### 8 · Replay history — *Version history* tab (45 s)

> "Every version is an immutable snapshot. So when you ask 'what did your system know before
> that last measurement?', I can show you the actual stored state — not a recomputation.
> Here is the diff between v8 and v9, on both the observed values and the predictions."

### 9 · Close on limits (30 s)

> "Everything shown is a model estimate for clinical decision support. The system does not
> diagnose, does not prescribe, and a counterfactual here shows how the model's expectation
> changes — not what would happen to the eye. Today it is trained on synthetic data, which
> the interface states on every screen. The pipeline is complete; connecting approved
> de-identified hospital data is a CSV and one retraining command."

---

## Questions you will get

**"Why a digital twin? Isn't this just an ML model?"**
> A static model gives one prediction from one input table. A twin maintains a persistent,
> versioned representation of one patient — current state, history, predicted future and
> what-if states. When a new observation arrives the twin updates instead of starting from
> zero, and any past version can be replayed. That is what version 8 → 9 demonstrated.

**"Where is the AI?"**
> Predictive AI for progression forecasting. Explainable AI for per-prediction attribution.
> Agentic AI for tool-using orchestration of retrieval, prediction, simulation and evidence.
> Generative AI, optionally, only to phrase facts the tools produced. Computer vision is a
> stretch module for non-medical-grade posture estimation.

**"Is this actually novel? Hasn't AI predicted myopia already?"**
> Yes, and we say so. A January 2026 *npj Digital Medicine* paper reports a large Transformer
> for personalized myopia progression and intervention prediction. We are not claiming to be
> first at prediction. Our contribution is the integration and engineering: an evolving
> versioned twin, calibrated uncertainty, ergonomic exposure modelling, a constrained
> counterfactual engine, an auditable tool-using agent and a reusable twin API. We will
> re-run the novelty search before final submission and phrase the claim against our own
> experiments.

**"How do you know the behaviour data helps?"**
> That is the ablation experiment on the Model card tab — clinical only, plus behaviour, plus
> ergonomics, on identical patient-level splits and identical hyperparameters. On synthetic
> data it is a demonstration of the method. On real data it is the actual experiment, and we
> will report the result in whichever direction it comes out.

**"Your R² is 0.99. That seems too good."**
> It is, and it is an artefact of synthetic data — the cohort is generated by a deterministic
> equation the model can nearly invert. That is why every metric is reported next to a
> carry-forward baseline, and why the interface labels the data as synthetic. We expect real
> performance to be substantially lower and we will report it honestly.

**"Can a clinician trust the what-if results?"**
> They are model estimates of an association learned from observational data, and the
> interface says that on every scenario. They are a structured way to explore what the model
> expects, not evidence that a behaviour change causes a clinical outcome. That distinction
> is enforced in the response payload itself, not just in the UI text.

**"Could you build the rest of it?"**
> The layers are already in place: longitudinal data, the model, twin state and the API
> underneath everything, then simulation and the agent. RAG and camera ergonomics are the
> stretch modules. The remaining work is connecting approved clinical data and hardening
> authentication — both documented in the README.
