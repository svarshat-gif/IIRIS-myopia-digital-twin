"""
Build the Capstone Phase-I Review-1 deck for the Myopia Digital Twin project.

Sources, and nothing else:
  * REVIEW_1_TEMPLATE_.pptx  -> slide order, section titles, table columns,
                                DSU branding, Bookman Old Style, 28pt titles
  * Myopia_Digital_Twin_Review_0.pdf -> project title, team, supervisors, and the
                                Introduction / Domain / Problem / Objectives /
                                Scope / Data content already presented
  * Myopia_Digital_Twin_Literature_Review.docx -> the 20 reviewed works, their
                                gaps, and the reference list

The template's own branding is preserved by lifting the four header logos out of
it and re-stamping them on every slide, so the deck is visually identical to the
one the department issued.
"""
from __future__ import annotations

import copy
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
UPLOADS = Path("/Users/riya/.claude/uploads/ef303b8d-d0da-406f-a783-7d6cfe7b1426")
TEMPLATE = UPLOADS / "a478982e-REVIEW_1_TEMPLATE_.docx.pptx"
ASSETS = HERE / "assets"
OUT = HERE / "Myopia_Digital_Twin_Review_1.pptx"

FONT = "Bookman Old Style"          # the template's font throughout
INK = RGBColor(0x12, 0x31, 0x4F)
BODY = RGBColor(0x1A, 0x1A, 0x1A)
ACCENT = RGBColor(0x1F, 0x6F, 0x9B)
RED = RGBColor(0xFF, 0x00, 0x00)
GREY = RGBColor(0x55, 0x5F, 0x69)
HEAD_BG = RGBColor(0x12, 0x31, 0x4F)
ROW_ALT = RGBColor(0xEF, 0xF3, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.55)
TITLE_TOP = Inches(1.08)
BODY_TOP = Inches(2.00)
BODY_BOTTOM = Inches(6.95)

FOOTER_TEXT = ("Capstone Phase-1 – 1st Review – 12.09.2026")
FOOTER_SUB = ("School of Engineering, Department of CSE (AI&ML), "
              "Dayananda Sagar University, Bengaluru - 562112.")


# --------------------------------------------------------------------------
# template scaffolding
# --------------------------------------------------------------------------

def load_template() -> tuple[Presentation, list[dict]]:
    """Open the template, remember the header logos, then clear its slides."""
    prs = Presentation(str(TEMPLATE))
    logos = []
    for shape in prs.slides[2].shapes:          # any content slide carries all four
        if shape.shape_type == 13:              # PICTURE
            logos.append({
                "blob": shape.image.blob,
                "ext": shape.image.ext,
                "left": shape.left, "top": shape.top,
                "width": shape.width, "height": shape.height,
            })
    logos.sort(key=lambda item: item["left"])

    thankyou = None
    for shape in prs.slides[16].shapes:
        if shape.shape_type == 13 and shape.width > Inches(3):
            thankyou = {"blob": shape.image.blob, "ext": shape.image.ext,
                        "left": shape.left, "top": shape.top,
                        "width": shape.width, "height": shape.height}

    # Drop every template slide; the deck is rebuilt from its layouts.
    id_list = prs.slides._sldIdLst
    for slide_id in list(id_list):
        rid = slide_id.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        prs.part.drop_rel(rid)
        id_list.remove(slide_id)

    for item in logos:
        path = ASSETS / f"logo_{item['left']}.{item['ext']}"
        path.write_bytes(item["blob"])
        item["path"] = path
    if thankyou:
        path = ASSETS / f"thankyou.{thankyou['ext']}"
        path.write_bytes(thankyou["blob"])
        thankyou["path"] = path
    return prs, logos, thankyou


def blank_slide(prs, logos, *, footer=True):
    slide = prs.slides.add_slide(prs.slide_layouts[6])   # Blank
    for item in logos:
        slide.shapes.add_picture(str(item["path"]), item["left"], item["top"],
                                 item["width"], item["height"])
    if footer:
        box = slide.shapes.add_textbox(MARGIN, Inches(6.98),
                                       SLIDE_W - 2 * MARGIN, Inches(0.42))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run(); run.text = FOOTER_TEXT
        run.font.size = Pt(8.5); run.font.name = FONT; run.font.color.rgb = GREY
        p2 = tf.add_paragraph()
        run2 = p2.add_run(); run2.text = FOOTER_SUB
        run2.font.size = Pt(7.5); run2.font.name = FONT; run2.font.color.rgb = GREY
    return slide


def add_title(slide, text, size=28):
    box = slide.shapes.add_textbox(MARGIN, TITLE_TOP, SLIDE_W - 2 * MARGIN,
                                   Inches(0.72))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    run = p.add_run(); run.text = text
    run.font.size = Pt(size); run.font.bold = True
    run.font.name = FONT; run.font.color.rgb = INK
    return box


def add_bullets(slide, items, *, size=18, top=None, height=None, left=None,
                width=None, space_after=10, bullet_char="• "):
    """items: str, or (text, level), or (text, level, bold)."""
    top = top if top is not None else BODY_TOP
    left = left if left is not None else MARGIN
    width = width if width is not None else SLIDE_W - 2 * MARGIN
    height = height if height is not None else (BODY_BOTTOM - top)

    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        text, level, bold = (item, 0, False) if isinstance(item, str) else (
            item + (False,) * (3 - len(item)))
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.level = level
        p.space_after = Pt(space_after)
        # python-pptx exposes indent only through the XML; level-1 items are
        # marked with a dash prefix instead, which reads the same on a slide.
        prefix = "" if bullet_char is None else (
            bullet_char if level == 0 else "– ")
        run = p.add_run()
        run.text = f"{prefix}{text}"
        run.font.size = Pt(size - 2 * level)
        run.font.name = FONT
        run.font.bold = bold
        run.font.color.rgb = INK if bold else BODY
    return box


def add_note(slide, text, *, top, size=9.5, color=None):
    box = slide.shapes.add_textbox(MARGIN, top, SLIDE_W - 2 * MARGIN, Inches(0.4))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run(); run.text = text
    run.font.size = Pt(size); run.font.name = FONT
    run.font.italic = True
    run.font.color.rgb = color or GREY
    return box


def add_table(slide, headers, rows, col_widths, *, top, height,
              head_size=10, body_size=8.5, row_height=None):
    total = sum(col_widths)
    left = int((SLIDE_W - Emu(int(total * 914400))) / 2)
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), left, top,
                                   Emu(int(total * 914400)), height)
    table = shape.table
    for i, w in enumerate(col_widths):
        table.columns[i].width = Inches(w)
    if row_height:
        for r in table.rows:
            r.height = Inches(row_height)

    for c, text in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = ""
        cell.fill.solid(); cell.fill.fore_color.rgb = HEAD_BG
        cell.margin_left = cell.margin_right = Inches(0.05)
        cell.margin_top = cell.margin_bottom = Inches(0.03)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run(); run.text = text
        run.font.size = Pt(head_size); run.font.bold = True
        run.font.name = FONT; run.font.color.rgb = WHITE

    for r, row in enumerate(rows, start=1):
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if r % 2 else ROW_ALT
            cell.margin_left = cell.margin_right = Inches(0.05)
            cell.margin_top = cell.margin_bottom = Inches(0.025)
            cell.vertical_anchor = MSO_ANCHOR.TOP
            p = cell.text_frame.paragraphs[0]
            run = p.add_run(); run.text = text
            run.font.size = Pt(body_size); run.font.name = FONT
            run.font.color.rgb = BODY
            if c == 0:
                run.font.bold = True
    return shape


# ==========================================================================
# content -- every fact below traces to Review-0 or the literature review doc
# ==========================================================================

PROJECT_TITLE = ('Myopia Digital Twin: Agentic AI-Based Progression Prediction '
                 'System with Biomarkers and Ergonomics')
COURSE_CODE = "23AM4701"          # as printed on the team's own Review-0 deck
ACADEMIC_YEAR = "2026-2027"
TEAM = [("T Kundana Svarsha", "ENG23AM0201"),
        ("Sneha Suman", "ENG23AM0196"),
        ("Srishti Gupta", "ENG23AM0198"),
        ("Reese Jayaprakas Pallath", "ENG23AM0178")]

CONTENTS = [
    "Introduction",
    "Domain & SDG Mapping",
    "Problem Statement",
    "Objectives",
    "Project Scope",
    "Source of Data Collection",
    "Expected Outcomes",
    "Tools & Technologies",
    "Methodology / Approach",
    "Timeline (Gantt Chart)",
    "References",
]

INTRODUCTION = [
    ("Background: Myopia progression is tracked through periodic clinical visits, so a "
     "patient's current prescription alone does not reveal how the condition is evolving.", 0),
    ("Motivation: Longitudinal ocular measurements, lifestyle behaviour and ergonomic "
     "factors are rarely combined into a single, continuously updated patient-specific model.", 0),
    ("Proposed approach: A Myopia Digital Twin — a continuously updated computational "
     "representation of each patient's ocular biomarkers (spherical equivalent, axial "
     "length), lifestyle factors (screen time, outdoor exposure) and ergonomic factors "
     "(viewing distance, posture).", 0),
    ("AI relevance: Supervised ML for progression prediction, a counterfactual simulation "
     "engine for what-if scenarios, SHAP for explainability, and an agentic AI layer that "
     "orchestrates prediction, evidence retrieval and monitoring.", 0),
    ("Current status: A working end-to-end prototype — “Iiris” — is already running: "
     "a React web application over a FastAPI Digital Twin service with 61 endpoints, "
     "trained models, a counterfactual simulator and a LangGraph agent layer.", 0),
]

DOMAIN = [
    ("Primary Domain: Healthcare AI / Medical AI — Clinical Decision Support.", 0),
    ("Predictive AI: Gradient-boosted models over 33 engineered longitudinal features "
     "predict 6- and 12-month spherical equivalent, axial length and progression risk.", 0),
    ("Explainable AI: SHAP TreeExplainer produces per-prediction feature attribution, "
     "presented with an explicit non-causal disclaimer.", 0),
    ("Agentic AI: A LangGraph graph (route → plan → execute → check → compose) drives "
     "12 declared tools; the agent can obtain facts only through those tools.", 0),
    ("Knowledge & Retrieval: RAG over Europe PMC / PubMed with a bundled offline corpus "
     "fallback, so every retrieved claim carries a citation.", 0),
    ("Interoperability: HL7 FHIR mapping of Patient and Observation records so the twin "
     "can exchange data with standard healthcare systems.", 0),
    ("SDG Alignment: SDG 3 — Good Health and Well-Being, supporting personalised, "
     "preventive eye-care decision support.", 0),
]

PROBLEM = [
    ("Problem: Existing myopia management relies on periodic measurements and "
     "population-level risk factors, without a continuously updated, patient-specific "
     "model of disease progression.", 0),
    ("Real-world challenge: A clinician can see the current prescription but has no simple "
     "way to explore how modifiable factors — outdoor time, screen exposure, viewing "
     "distance — might change that patient's future trajectory.", 0),
    ("Research gap: Heterogeneous datasets, limited external validation, and insufficient "
     "integration of longitudinal ocular biomarkers with behavioural and ergonomic factors.", 0),
    ("Proposed solution: A Digital Twin that maintains each patient's evolving state, "
     "predicts short- and long-term progression with uncertainty, and runs model-based "
     "counterfactual simulations of lifestyle and ergonomic change.", 0),
    ("Boundary: A clinical decision-support tool with the clinician in the loop — it does "
     "not diagnose and does not autonomously prescribe treatment.", 0),
]

OBJECTIVES = [
    ("O1 — Implement a Myopia Digital Twin holding a continuously updated, versioned, "
     "patient-specific state.   [ACHIEVED — immutable version written on every visit]", 0),
    ("O2 — Prepare a structured longitudinal dataset with patient-level splitting, "
     "temporal feature engineering and principled missing-value handling.   "
     "[ACHIEVED on the synthetic cohort; real-data onboarding in progress]", 0),
    ("O3 — Develop and compare ML models to predict 6- and 12-month spherical equivalent, "
     "axial length and progression risk (MAE, RMSE, R², ROC-AUC, PR-AUC).   "
     "[ACHIEVED — five model families compared on identical splits]", 0),
    ("O4 — Build a counterfactual simulation engine with a plausibility gate, and apply "
     "SHAP for per-prediction explainability.   [ACHIEVED — plus a 1–8 year projection "
     "engine with compounding uncertainty]", 0),
    ("O5 — Develop a LangGraph agentic layer with RAG evidence retrieval, exposed through "
     "a FastAPI Digital Twin API and a dashboard.   [ACHIEVED — 61 endpoints, 12 agent "
     "tools, 58 automated tests passing]", 0),
    ("O6 — Validate on approved, de-identified clinical data and report external "
     "performance.   [IN PROGRESS — the remaining objective for Phase-II]", 0),
]

SCOPE = [
    ("Covered — Data: Pre-processing of longitudinal clinical, behavioural and ergonomic "
     "data; 33 engineered temporal features; patient-level splitting to prevent leakage.", 0),
    ("Covered — Modelling: HistGradientBoosting deployed, benchmarked against XGBoost, "
     "LightGBM, Random Forest, Ridge and a carry-forward baseline, with conformally "
     "calibrated prediction intervals and SHAP explanations.", 0),
    ("Covered — Twin & API: Versioned twin state (current, historical, predicted) behind "
     "a 61-endpoint FastAPI service with per-user accounts, JWT sessions and FHIR export.", 0),
    ("Covered — Simulation & Agents: Counterfactual engine with a plausibility gate, a "
     "1–8 year projection engine, and a LangGraph agent layer over 12 declared tools with "
     "RAG evidence retrieval.", 0),
    ("Optional Extension: Camera-based ergonomic estimation (MediaPipe) and "
     "LSTM/Transformer temporal models, if sufficient longitudinal sequences are available.", 0),
    ("Not Covered: Causal treatment claims, autonomous prescription, OCT/fundus imaging "
     "pipelines, and real clinical deployment — left to future phases.", 0),
    ("Application Domain: Healthcare AI — paediatric ophthalmology decision support "
     "(SDG 3).", 0),
]

LIT_HEADERS = ["Paper Title", "Algorithm", "Dataset", "Metrics", "Research Gap"]
LIT_COLS = [3.05, 2.15, 2.35, 2.05, 2.80]

LITERATURE = [
    ("[1] Huang et al. (2023), Scientific Reports — Time-aware deep learning "
     "[BASE PAPER]",
     "Time-aware deep learning over sequential visits",
     "Longitudinal paediatric refraction records",
     "Future myopia status prediction",
     "Black-box model; no behavioural or ergonomic layer; no way to test hypothetical "
     "interventions"),
    ("[2] Liu et al. (2026), npj Digital Medicine — AI-guided personalized myopia "
     "predictions (MPPM)",
     "Transformer: natural-progression + intervention modules, causal ML",
     "1,109,827 refractive records from 304,353 children and adolescents",
     "SE R² 0.94, MAE 0.35 D; AL R² 0.91, MAE 0.16 mm",
     "Population-scale predictor; no persistent per-patient state, no prediction "
     "interval, no clinician-facing API"),
    ("[3] Kang et al. (2026), JAMA Network Open — deep learning myopia progression",
     "ResNet-34 CNN + LSTM on fundus image sequences",
     "Anyang cohort with Lhasa and Beijing external validation; fundus images + "
     "baseline refraction",
     "AUC for progression and high-myopia risk",
     "Requires fundus imaging; no behavioural or ergonomic layer; no what-if simulation"),
    ("[4] Li J et al. (2024), Precision Clinical Medicine — ML prediction of myopic "
     "progression",
     "Multivariate linear regression",
     "612,530 records from 227,543 patients across five cohorts",
     "R² 0.964, MAE 0.119 D internal; high-myopia AUC 0.99",
     "Single-shot prediction; no intervention simulation and no evolving patient state"),
    ("[5] Gao et al. (2025), Frontiers in Medicine — myopia onset in premyopic children",
     "Machine learning with SHAP interpretation",
     "320 premyopic children aged 6–12, 12-month follow-up",
     "AUC-ROC 0.963 for 1-year myopia onset",
     "Onset only at a 1-year horizon, single centre; no continuing twin state"),
    ("[6] Hu et al. (2025), Scientific Reports — biometric + multimodal imaging",
     "Deep feature extraction from OCT and fundus photography + XGBoost",
     "472 eyes from 347 subjects aged 6–14; OCT, CFP and biometry",
     "AUROC 0.845 ± 0.050",
     "Needs imaging infrastructure; predicts onset only, with no trajectory or "
     "simulation"),
    ("[7] Zhang X et al. (2025), Scientific Reports — fundus imageomics",
     "LASSO selection + Random Forest / XGBoost / LightGBM",
     "2,184 colour fundus photographs, children aged 6–10",
     "RF AUC 0.798; specificity 0.80, sensitivity 0.59",
     "Cross-sectional and imaging-dependent; no longitudinal state or uncertainty"),
    ("[8] Liang et al. (2025), British Journal of Ophthalmology — global prevalence to "
     "2050",
     "Systematic review, meta-analysis and projection modelling",
     "Pooled global studies, 1990–2050 projection",
     "Global prevalence estimates and 2050 projection",
     "Epidemiological motivation only; produces no individual predictive model"),
    ("[9] Lawrenson et al. (2025), Cochrane Database — myopia control network "
     "meta-analysis",
     "Living systematic review + network meta-analysis",
     "Pooled randomised trials of myopia-control interventions",
     "Relative efficacy ranking across interventions",
     "Average treatment effects; no way to estimate the effect for one patient before "
     "it is tried"),
    ("[10] Yam et al. (2025), Progress in Retinal and Eye Research — interventions "
     "review",
     "Comprehensive evidence review",
     "Surveyed intervention trials in children and adults",
     "Not applicable (review)",
     "Review only; does not build a predictive or patient-specific system"),
    ("[11] Kido et al. (2024), Cochrane Database — time spent outdoors",
     "Systematic review of randomised interventions",
     "Trials increasing children's outdoor time",
     "Effect on myopia incidence and progression",
     "Population effect; offers no mechanism to estimate it for one child"),
    ("[12] Chen et al. (2024), JAMA Network Open — smartwatch outdoor exposure",
     "Prospective cohort with objective wearable sensing",
     "STORM sub-study, Shanghai schoolchildren wearing smartwatches ≥6 h/day",
     "Association of outdoor exposure pattern with myopic shift",
     "Observational association; no predictive or simulation system built on it"),
    ("[13] Zougheib et al. (2026), PLOS ONE — screen time and outdoor activity",
     "Observational association analysis",
     "Children with recorded screen-time and outdoor-activity exposure",
     "Association with myopia progression",
     "Population association; no individual-level model"),
    ("[14] Biswas et al. (2024), Journal of Physiological Anthropology — environment "
     "and lifestyle",
     "Narrative review",
     "Surveyed environmental and lifestyle literature",
     "Not applicable (review)",
     "Justifies which exposures to capture but implements nothing"),
    ("[15] Laubenbacher et al. (2024), Nature Computational Science — digital twins in "
     "medicine",
     "Conceptual overview of medical digital twins",
     "Not applicable",
     "Not applicable (review)",
     "Focused on oncology and cardiology; no ophthalmic instantiation"),
    ("[16] Sadée et al. (2025), The Lancet Digital Health — medical digital twins",
     "Health-policy framework: five components of a medical digital twin",
     "Not applicable",
     "Not applicable (framework)",
     "Defines the concept but implements no domain-specific twin"),
    ("[17] Mehandru et al. (2024), npj Digital Medicine — LLM agents in the clinic",
     "Evaluation framework for LLM-based clinical agents",
     "Clinical agent evaluation scenarios",
     "Agent evaluation criteria",
     "General clinical agents; no myopia grounding and no numeric guardrail on output"),
    ("[18] Ferber et al. (2026), Nature — autonomous medical AI agents",
     "Architectures for autonomous medical AI agents",
     "Not applicable",
     "Not applicable (perspective)",
     "Forward-looking; no concrete paediatric ophthalmology implementation"),
    ("[19] Ponce-Bobadilla et al. (2024), Clinical and Translational Science — SHAP in "
     "practice",
     "SHAP (Shapley additive explanations) applied to clinical models",
     "Drug-development model examples",
     "Attribution consistency and interpretation guidance",
     "Method guidance only; no myopia application and no causal guarantee"),
    ("[20] Parreño et al. (2026), Computer Methods and Programs in Biomedicine — "
     "conformal XGBoost",
     "Conformal prediction wrapped around XGBoost",
     "Sepsis survival cohort under Sepsis-3 criteria",
     "Calibrated coverage with minimal clinical features",
     "Demonstrates calibrated uncertainty in another specialty; not applied to myopia "
     "or to a longitudinal twin"),
]

LIT_NOTE = ("19 of the 20 works reviewed are from 2024\u20132026; [1] is retained as the "
            "base paper. Full citations, with DOI links, are listed under References.")

BASE_PAPER_ROW = [
    ("[1] Huang et al. (2023), “Myopia prediction for children and adolescents via "
     "time-aware deep learning,” Scientific Reports, vol. 13, 5430",
     "Time-aware deep learning over sequential visits",
     "Longitudinal paediatric refraction records",
     "Future myopia status prediction",
     "Black-box model; no behavioural or ergonomic layer; no uncertainty interval; no "
     "way to test hypothetical interventions; no persistent patient state or API"),
]

NOVELTY = [
    ("Evolving, versioned twin — state is re-versioned at every visit and any past "
     "state can be replayed; the base paper predicts once per input table.", 0),
    ("Uncertainty-aware — conformally calibrated prediction intervals validated on "
     "unseen patients, not a single point estimate.", 0),
    ("Behavioural + ergonomic digital phenotype — screen time, near work, outdoor "
     "exposure, viewing distance, posture and session length as model inputs.", 0),
    ("Counterfactual what-if engine with a plausibility gate — implausible scenarios "
     "are rejected, not answered with a confident-looking number.", 0),
    ("Explainable and evidence-grounded — SHAP attribution per prediction plus "
     "RAG-retrieved citations, both explicitly labelled non-causal.", 0),
    ("Agentic orchestration and a reusable API — LangGraph tool-using agents behind a "
     "FHIR-mapped FastAPI Digital Twin API, not a dashboard around a model.", 0),
]

METHODOLOGY_STEPS = [
    ("Ingest longitudinal clinical, behavioural and ergonomic observations", 0),
    ("Clean, validate, build temporal features; split by patient", 0),
    ("Update the versioned twin state on every new observation", 0),
    ("Predict 6/12-month SE and AL with intervals; attribute with SHAP", 0),
    ("Clone the twin, apply a what-if change, re-run the model, compare", 0),
    ("Orchestrate via LangGraph agents and RAG; expose through the API", 0),
]

DATA_SOURCES = [
    ("Stage 1 — Synthetic data (in use now): A purpose-built generator produces 600 "
     "patients over 8 six-monthly visits, so the whole pipeline can be built and tested "
     "before any real data is available. It is labelled synthetic everywhere it appears.", 0),
    ("Stage 2 — Testing phase on public data: Open myopia datasets (Kaggle and public "
     "research repositories) are used to test the pipeline on real measurements and check "
     "that it holds up beyond the generator.", 0),
    ("Stage 3 — Real hospital data: De-identified longitudinal clinical records — "
     "spherical equivalent, axial length, visual acuity and treatment history across "
     "multiple visits — obtained under institutional approval and consent.", 0),
    ("One contract at every stage: patient_key, visit_date, spherical_equivalent and "
     "axial_length are required; behaviour and ergonomic fields are optional and stay "
     "missing when not collected. Moving between stages is one CSV and one retraining "
     "command — no code changes.", 0),
    ("Full traceability: every patient in the running application — including the two "
     "demo sign-in accounts — is loaded directly from that CSV, so any figure on screen "
     "can be located in the dataset submitted with this report.", 0),
    ("Ethics & privacy: De-identification at source, institutional approval for any "
     "hospital data, role-based access and encryption; outputs framed as decision "
     "support, never diagnosis.", 0),
]

TOOLS = [
    ("Language & runtime: Python 3.11+ (backend, ML, simulation); JavaScript / JSX "
     "(frontend). No GPU required — everything trains and runs on a standard laptop.", 0),
    ("Machine learning: scikit-learn 1.6 (HistGradientBoosting — deployed), XGBoost 3.4 "
     "and LightGBM 4.7 (benchmark comparison), NumPy 2.2, Pandas 2.2, joblib.", 0),
    ("Explainability: SHAP 0.52 (TreeExplainer) for per-prediction attribution; "
     "permutation importance for global ranking.", 0),
    ("Backend & API: FastAPI 0.115 + Uvicorn 0.34, Pydantic 2.10 validation, "
     "SQLAlchemy 2.0 ORM, auto-generated OpenAPI/Swagger documentation.", 0),
    ("Security: PyJWT 2.10 session tokens, PBKDF2-HMAC-SHA256 password hashing "
     "(480,000 iterations), per-user record isolation, magic-byte file validation.", 0),
    ("Agentic & retrieval: LangGraph 0.6 orchestration over 12 declared tools; httpx "
     "clients for Europe PMC and PubMed E-utilities; optional local LLM via Ollama.", 0),
    ("Database & interoperability: SQLite for development, PostgreSQL for deployment; "
     "HL7 FHIR R4 JSON export of Patient and Observation resources.", 0),
    ("Frontend: React 18, Vite 6, React Router 7, Tailwind CSS 3, Chart.js 4 "
     "(react-chartjs-2) for trajectory and uncertainty visualisation.", 0),
    ("Tooling: pytest (58 tests), Docker + docker-compose, Git/GitHub, Google Colab for "
     "heavier training runs.", 0),
]

OUTCOMES = [
    ("Achieved — A functional Myopia Digital Twin prototype (“Iiris”) maintaining a "
     "versioned patient state that advances on every new observation.", 0),
    ("Achieved — Progression models for 6- and 12-month SE, axial length and risk, "
     "reported on patient-level held-out data against a carry-forward baseline and four "
     "competing model families.", 0),
    ("Achieved — A counterfactual simulator and a 1–8 year projection engine producing "
     "baseline-versus-scenario trajectories with calibrated, widening intervals and an "
     "explicit non-causal disclaimer.", 0),
    ("Achieved — The ablation study comparing clinical-only, +behaviour and "
     "+ergonomics feature sets on identical splits.", 0),
    ("Achieved — A 61-endpoint Digital Twin API with FHIR Patient/Observation export, "
     "per-user accounts and a clinician-facing dashboard, covered by 58 automated tests.", 0),
    ("Remaining (Phase-II) — Validation on approved, de-identified clinical data; "
     "external performance reporting; and a capstone technical report plus a manuscript "
     "draft on patient-specific digital twins for myopia decision support (SDG 3).", 0),
]


# ---------- implemented-system slides ----------

IMPLEMENTATION = [
    ("Digital Twin state — every new observation writes an immutable version "
     "(v1, v2, v3 …). Any past state can be replayed exactly, and two versions can be "
     "diffed to flag a material change in the predicted trajectory.", 0),
    ("Prediction with honest uncertainty — quantile models are split-conformally "
     "calibrated on a held-out set of patients, lifting measured interval coverage from "
     "0.72–0.77 to 0.91–0.93 against a nominal 0.90.", 0),
    ("Counterfactual simulator — clones the twin, applies an exposure change, rebuilds "
     "features with the same builder used in training and re-runs the same model. "
     "Implausible values are rejected with an error, never answered.", 0),
    ("Projection engine — rolls the twin forward 1–8 years autoregressively, widening the "
     "interval in quadrature at each step and downgrading the stated confidence from "
     "“modelled” to “projected” to “indicative”.", 0),
    ("Agentic layer — a LangGraph graph over 12 declared tools. The agent obtains facts "
     "only through tools; when a local LLM is attached, every number it writes must trace "
     "back to tool output or the generated text is discarded.", 0),
    ("Web application — accounts with JWT sessions, per-user record isolation, "
     "prescription photo upload with magic-byte validation, appointments, and FHIR export. "
     "58 automated tests cover the whole loop.", 0),
]

RESULTS_HEADERS = ["Target", "Deployed\n(HistGB)", "XGBoost", "LightGBM",
                   "Random\nForest", "Ridge", "Carry-\nforward"]
RESULTS_COLS = [2.55, 1.65, 1.45, 1.45, 1.45, 1.35, 1.55]
RESULTS_ROWS = [
    ("Spherical equivalent @ 6 m (MAE, D)", "0.070", "0.067", "0.067", "0.067",
     "0.052", "0.188"),
    ("Spherical equivalent @ 12 m (MAE, D)", "0.106", "0.103", "0.105", "0.115",
     "0.078", "0.374"),
    ("Axial length @ 6 m (MAE, mm)", "0.039", "0.039", "0.040", "0.040",
     "0.035", "0.095"),
    ("Axial length @ 12 m (MAE, mm)", "0.060", "0.059", "0.060", "0.063",
     "0.052", "0.187"),
]

RESULTS_NOTES = [
    ("Held-out test set of 120 patients (train 384 / validation 96), split by patient so "
     "no child appears in two splits. Progression-risk classifier: ROC-AUC 0.918, "
     "PR-AUC 0.812, Brier 0.093.", 0),
    ("Every model beats the carry-forward baseline (“assume nothing changes”) by a wide "
     "margin — the only comparison that shows a predictive model is worth having.", 0),
    ("Ridge currently has the lowest MAE because the synthetic generator is close to "
     "linear in its features. We report this rather than hide it; on real, noisier data "
     "the tree ensembles are expected to lead. HistGradientBoosting is deployed because "
     "it is the model that also supports quantile loss (needed for the interval) and NaN "
     "inputs (needed because behaviour is often unrecorded).", 0),
]

CALIBRATION = [
    ("Uncertainty calibration — raw quantile regression under-covered badly. A "
     "split-conformal correction fitted on validation patients repairs it:", 0),
    ("Spherical equivalent @ 6 m:  0.754  →  0.912          "
     "Axial length @ 6 m:  0.773  →  0.926", 1),
    ("Spherical equivalent @ 12 m: 0.722  →  0.908          "
     "Axial length @ 12 m: 0.731  →  0.918", 1),
    ("A stated “90% interval” now means approximately 90%. Without this step the system "
     "would have looked far more confident than it is.", 0),
    ("Ablation (identical splits, identical hyper-parameters) — does behaviour and "
     "ergonomics add value over biomarkers alone?", 0),
    ("Clinical only:  SE-12m MAE 0.109 · AL-12m MAE 0.060 · risk ROC-AUC 0.893", 1),
    ("+ behaviour:    SE-12m MAE 0.112 · AL-12m MAE 0.062 · risk ROC-AUC 0.884", 1),
    ("+ ergonomics:   SE-12m MAE 0.106 · AL-12m MAE 0.060 · risk ROC-AUC 0.915", 1),
    ("Reading it honestly: behaviour alone does not help regression on this cohort; the "
     "full set improves progression-risk classification. On synthetic data this "
     "demonstrates the experiment, not a clinical finding — the same protocol will be "
     "re-run on real data.", 0),
    ("Known limitation — the tail: the quantile and median models are fitted "
     "independently, so where the cohort thins out (below about −4 D) they begin to "
     "disagree and the point estimate sits near the edge of its own interval. Measured: "
     "well centred for 98% of rows between −1 and −3 D, off-centre for 55% below "
     "−4 D. The API detects and reports this per record rather than hiding it.", 0),
]

PROTOTYPE_CAPTIONS = [
    "Home — cohort patient SYN00532: measured history, forecast with a 90% "
    "band, risk and next appointment",
    "Simulator — baseline vs “two hours outdoors”, projected five years ahead",
]

SYNTHETIC_WARNING = ("All figures on this slide come from the SYNTHETIC development "
                     "cohort. They demonstrate that the pipeline works end to end; they "
                     "are not clinical performance results.")

REFERENCES_1 = [
    ("[1]  J. Huang et al., “Myopia prediction for children and adolescents via "
     "time-aware deep learning,” Scientific Reports, vol. 13, 5430, 2023.   "
     "[BASE PAPER]", "https://doi.org/10.1038/s41598-023-32367-0"),
    ("[2]  S. Liu et al., “AI-guided personalized predictions on myopia progression "
     "and interventions,” npj Digital Medicine, vol. 9, 129, 2026.",
     "https://doi.org/10.1038/s41746-025-02308-4"),
    ("[3]  M. T. Kang et al., “Deep Learning Prediction of Childhood Myopia "
     "Progression Using Fundus Image and Refraction Data,” JAMA Network Open, "
     "vol. 9, e2553543, 2026.",
     "https://doi.org/10.1001/jamanetworkopen.2025.53543"),
    ("[4]  J. Li et al., “Accurate prediction of myopic progression and high myopia "
     "by machine learning,” Precision Clinical Medicine, vol. 7, pbae005, 2024.",
     "https://doi.org/10.1093/pcmedi/pbae005"),
    ("[5]  M. Gao et al., “Prediction of myopia onset and shift in premyopic "
     "school-aged children: a machine learning-based algorithm,” Frontiers in "
     "Medicine, vol. 12, 1646277, 2025.",
     "https://doi.org/10.3389/fmed.2025.1646277"),
    ("[6]  M. Hu et al., “Integrating biometric and multimodal imaging data for early "
     "prediction of myopia onset,” Scientific Reports, vol. 15, 31416, 2025.",
     "https://doi.org/10.1038/s41598-025-15605-5"),
    ("[7]  X. Zhang et al., “Predicting myopia risk using a machine learning model "
     "based on fundus imageomics,” Scientific Reports, vol. 15, 43729, 2025.",
     "https://doi.org/10.1038/s41598-025-27848-3"),
    ("[8]  J. Liang et al., “Global prevalence, trend and projection of myopia in "
     "children and adolescents from 1990 to 2050: a systematic review and "
     "meta-analysis,” British Journal of Ophthalmology, vol. 109, no. 3, "
     "pp. 362–371, 2025.", "https://doi.org/10.1136/bjo-2024-325427"),
    ("[9]  J. G. Lawrenson et al., “Interventions for myopia control in children: a "
     "living systematic review and network meta-analysis,” Cochrane Database of "
     "Systematic Reviews, vol. 2, CD014758, 2025.",
     "https://doi.org/10.1002/14651858.CD014758.pub3"),
    ("[10] J. C. Yam et al., “Interventions to reduce incidence and progression of "
     "myopia in children and adults,” Progress in Retinal and Eye Research, "
     "vol. 109, 101410, 2025.",
     "https://doi.org/10.1016/j.preteyeres.2025.101410"),
]

REFERENCES_2 = [
    ("[11] A. Kido et al., “Interventions to increase time spent outdoors for "
     "preventing incidence and progression of myopia in children,” Cochrane "
     "Database of Systematic Reviews, vol. 6, CD013549, 2024.",
     "https://doi.org/10.1002/14651858.CD013549.pub2"),
    ("[12] J. Chen et al., “Smartwatch Measures of Outdoor Exposure and Myopia in "
     "Children,” JAMA Network Open, vol. 7, no. 8, e2424595, 2024.",
     "https://doi.org/10.1001/jamanetworkopen.2024.24595"),
    ("[13] Y. Zougheib et al., “Effect of screen time and outdoor activities on "
     "myopia progression,” PLOS ONE, vol. 21, no. 5, e0347118, 2026.",
     "https://doi.org/10.1371/journal.pone.0347118"),
    ("[14] S. Biswas et al., “The influence of the environment and lifestyle on "
     "myopia,” Journal of Physiological Anthropology, vol. 43, 7, 2024.",
     "https://doi.org/10.1186/s40101-024-00354-7"),
    ("[15] R. Laubenbacher et al., “Digital twins in medicine,” Nature Computational "
     "Science, vol. 4, pp. 184–191, 2024.",
     "https://doi.org/10.1038/s43588-024-00607-6"),
    ("[16] C. Sadée et al., “Medical digital twins: enabling precision medicine and "
     "medical artificial intelligence,” The Lancet Digital Health, vol. 7, 100864, "
     "2025.", "https://doi.org/10.1016/j.landig.2025.02.004"),
    ("[17] N. Mehandru et al., “Evaluating large language models as agents in the "
     "clinic,” npj Digital Medicine, vol. 7, 84, 2024.",
     "https://doi.org/10.1038/s41746-024-01083-y"),
    ("[18] D. Ferber et al., “Towards autonomous medical artificial intelligence "
     "agents,” Nature, vol. 655, pp. 1282–1291, 2026.",
     "https://doi.org/10.1038/s41586-026-10675-5"),
    ("[19] A. V. Ponce-Bobadilla et al., “Practical guide to SHAP analysis: Explaining "
     "supervised machine learning model predictions in drug development,” Clinical "
     "and Translational Science, vol. 17, no. 11, e70056, 2024.",
     "https://doi.org/10.1111/cts.70056"),
    ("[20] S. J. Parreño et al., “Uncertainty-aware sepsis survival prediction using "
     "conformal XGBoost on minimal clinical features under Sepsis-3 criteria,” "
     "Computer Methods and Programs in Biomedicine, vol. 283, 109429, 2026.",
     "https://doi.org/10.1016/j.cmpb.2026.109429"),
]


# ==========================================================================
# slide builders
# ==========================================================================

def slide_title(prs, logos):
    slide = blank_slide(prs, logos, footer=False)

    box = slide.shapes.add_textbox(Inches(0.68), Inches(1.05),
                                   Inches(12.0), Inches(1.10))
    tf = box.text_frame; tf.word_wrap = True
    for i, (text, size) in enumerate([
            ("Dayananda Sagar University (DSU) - Main Campus", 24),
            ("School of Engineering", 24),
            ("Devarakaggalahalli, Harohalli Kanakapura Road, Bengaluru South Dist., "
             "Karnataka 562112", 12)]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.bold = True; r.font.name = FONT
        r.font.color.rgb = INK

    box = slide.shapes.add_textbox(Inches(0.26), Inches(2.18),
                                   Inches(12.8), Inches(1.72))
    tf = box.text_frame; tf.word_wrap = True
    lines = [("DEPARTMENT OF", None), ("COMPUTER SCIENCE AND ENGINEERING", None),
             ("(ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING)", None),
             (f"Capstone Project Phase-I({COURSE_CODE})", None), ("Review-1", RED)]
    for i, (text, colour) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = text
        r.font.size = Pt(20); r.font.bold = True; r.font.name = FONT
        r.font.color.rgb = colour or INK

    box = slide.shapes.add_textbox(Inches(0.34), Inches(3.96),
                                   Inches(12.65), Inches(0.75))
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = f"Title: “{PROJECT_TITLE}”"
    r.font.size = Pt(18); r.font.bold = True; r.font.name = FONT
    r.font.color.rgb = INK

    box = slide.shapes.add_textbox(Inches(0.34), Inches(4.86),
                                   Inches(5.4), Inches(1.5))
    tf = box.text_frame; tf.word_wrap = True
    sup = [("Under the Supervision of", True),
           ("Ankita Thakkar, Assistant Professor", False),
           ("Pragnya Mishra, Assistant Professor (Co-Supervisor)", False),
           ("Department of CSE (AI&ML), SOE, DSU.", False)]
    for i, (text, bold) in enumerate(sup):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = text
        r.font.size = Pt(14); r.font.bold = bold; r.font.name = FONT
        r.font.color.rgb = INK

    # Names and USNs go in two boxes: space-padding does not align in a
    # proportional font like Bookman Old Style.
    names_box = slide.shapes.add_textbox(Inches(7.30), Inches(4.86),
                                         Inches(3.6), Inches(1.5))
    usn_box = slide.shapes.add_textbox(Inches(10.95), Inches(4.86),
                                       Inches(2.1), Inches(1.5))
    tf_n, tf_u = names_box.text_frame, usn_box.text_frame
    tf_n.word_wrap = tf_u.word_wrap = True
    for i, (name, usn) in enumerate(TEAM):
        pn = tf_n.paragraphs[0] if i == 0 else tf_n.add_paragraph()
        rn = pn.add_run(); rn.text = name
        rn.font.size = Pt(14); rn.font.name = FONT; rn.font.color.rgb = INK
        pu = tf_u.paragraphs[0] if i == 0 else tf_u.add_paragraph()
        ru = pu.add_run(); ru.text = usn
        ru.font.size = Pt(14); ru.font.name = FONT; ru.font.color.rgb = INK

    box = slide.shapes.add_textbox(Inches(3.11), Inches(6.52),
                                   Inches(6.67), Inches(0.45))
    tf = box.text_frame
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = f"Academic Year: {ACADEMIC_YEAR}"
    r.font.size = Pt(14); r.font.bold = True; r.font.name = FONT
    r.font.color.rgb = INK

    box = slide.shapes.add_textbox(Inches(0.34), Inches(6.95),
                                   Inches(12.65), Inches(0.4))
    tf = box.text_frame
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = "SDG TITLE ALIGNED: SDG 3 – Good Health and Well-Being"
    r.font.size = Pt(12); r.font.bold = True; r.font.name = FONT
    r.font.color.rgb = ACCENT
    return slide


def slide_contents(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Contents")
    left = slide.shapes.add_textbox(MARGIN, BODY_TOP, Inches(6.0), Inches(4.8))
    right = slide.shapes.add_textbox(Inches(6.9), BODY_TOP, Inches(6.0), Inches(4.8))
    half = (len(CONTENTS) + 1) // 2
    for box, chunk, start in ((left, CONTENTS[:half], 1),
                              (right, CONTENTS[half:], half + 1)):
        tf = box.text_frame; tf.word_wrap = True
        for i, item in enumerate(chunk):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(11)
            r = p.add_run(); r.text = f"{start + i}.  {item}"
            r.font.size = Pt(18); r.font.name = FONT; r.font.color.rgb = BODY
    return slide


def slide_bullets(prs, logos, title, items, *, size=18, note=None, title_size=28):
    slide = blank_slide(prs, logos)
    add_title(slide, title, size=title_size)
    height = (BODY_BOTTOM - BODY_TOP) - (Inches(0.42) if note else 0)
    add_bullets(slide, items, size=size, height=height)
    if note:
        add_note(slide, note, top=BODY_BOTTOM - Inches(0.38))
    return slide


def slide_literature(prs, logos, entries):
    slide = blank_slide(prs, logos)
    add_title(slide, "Literature Review")
    add_table(slide, LIT_HEADERS, entries, LIT_COLS,
              top=Inches(1.92), height=Inches(4.6),
              head_size=10, body_size=8.0)
    add_note(slide, LIT_NOTE, top=Inches(6.62), size=8.5)
    return slide


def slide_base_paper(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Base Paper and Novelty of the Proposed Work")

    box = slide.shapes.add_textbox(MARGIN, Inches(1.82), SLIDE_W - 2 * MARGIN,
                                   Inches(0.3))
    p = box.text_frame.paragraphs[0]
    r = p.add_run(); r.text = "Base Paper"
    r.font.size = Pt(15); r.font.bold = True; r.font.name = FONT
    r.font.color.rgb = ACCENT

    add_table(slide, LIT_HEADERS, BASE_PAPER_ROW, LIT_COLS,
              top=Inches(2.16), height=Inches(1.15),
              head_size=9.5, body_size=8.0)

    box = slide.shapes.add_textbox(MARGIN, Inches(3.62), SLIDE_W - 2 * MARGIN,
                                   Inches(0.3))
    p = box.text_frame.paragraphs[0]
    r = p.add_run(); r.text = "Novelty of the Proposed Work"
    r.font.size = Pt(15); r.font.bold = True; r.font.name = FONT
    r.font.color.rgb = ACCENT

    add_bullets(slide, NOVELTY, size=12, top=Inches(3.94),
                height=Inches(2.6), space_after=5)
    return slide


def slide_methodology(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Methodology / Approach")
    pic = ASSETS / "workflow.png"
    # Fit the diagram to the body area, preserving aspect ratio.
    from PIL import Image  # noqa: PLC0415
    with Image.open(pic) as im:
        ar = im.width / im.height
    avail_w, avail_h = Inches(11.9), Inches(3.95)
    w = avail_w
    h = int(w / ar)
    if h > avail_h:
        h = avail_h; w = int(h * ar)
    slide.shapes.add_picture(str(pic), int((SLIDE_W - w) / 2), Inches(1.80), w, h)
    steps_top = Inches(1.80) + h + Inches(0.14)
    add_bullets(slide, METHODOLOGY_STEPS[:3], size=11, top=steps_top,
                height=Inches(0.78), width=Inches(6.15), space_after=3)
    add_bullets(slide, METHODOLOGY_STEPS[3:], size=11, top=steps_top,
                left=Inches(6.95), height=Inches(0.78), width=Inches(5.9),
                space_after=3)
    return slide


def slide_gantt(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Timeline (Gantt Chart)")
    pic = ASSETS / "gantt.png"
    from PIL import Image  # noqa: PLC0415
    with Image.open(pic) as im:
        ar = im.width / im.height
    avail_w, avail_h = Inches(12.2), Inches(4.6)
    w = avail_w; h = int(w / ar)
    if h > avail_h:
        h = avail_h; w = int(h * ar)
    slide.shapes.add_picture(str(pic), int((SLIDE_W - w) / 2), Inches(1.84), w, h)
    add_bullets(slide, [
        ("Review-0 delivered the problem statement and the proposed solution approach.", 0),
        ("Review-1 delivers the literature survey (20 papers) and the base-paper "
         "selection with the novelty of the proposed work.", 0),
        ("Prototype implementation began early and is running ahead of plan; dataset "
         "approval is now the critical path to Phase-II.", 0),
    ], size=11.5, top=Inches(6.20), height=Inches(1.0), space_after=2)
    return slide


def slide_references(prs, logos, items, size=11):
    """Each entry is (citation, url); the URL is a real PowerPoint hyperlink."""
    slide = blank_slide(prs, logos)
    add_title(slide, "References")
    box = slide.shapes.add_textbox(MARGIN, BODY_TOP, SLIDE_W - 2 * MARGIN,
                                   BODY_BOTTOM - BODY_TOP)
    tf = box.text_frame
    tf.word_wrap = True
    for i, (text, url) in enumerate(items):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(5)
        run = para.add_run()
        run.text = text + "  "
        run.font.size = Pt(size); run.font.name = FONT; run.font.color.rgb = BODY
        link = para.add_run()
        link.text = url.replace("https://", "")
        link.font.size = Pt(size - 0.5); link.font.name = FONT
        link.hyperlink.address = url
        link.font.color.rgb = ACCENT
        link.font.underline = True
    return slide


def slide_thankyou(prs, logos, thankyou):
    slide = blank_slide(prs, logos, footer=False)
    if thankyou:
        slide.shapes.add_picture(str(thankyou["path"]), thankyou["left"],
                                 thankyou["top"], thankyou["width"],
                                 thankyou["height"])
    else:
        box = slide.shapes.add_textbox(MARGIN, Inches(3.0), SLIDE_W - 2 * MARGIN,
                                       Inches(1.2))
        p = box.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = "Thank You"
        r.font.size = Pt(44); r.font.bold = True; r.font.name = FONT
        r.font.color.rgb = INK
    return slide



def slide_architecture(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "System Architecture (as implemented)")
    pic = ASSETS / "architecture.png"
    from PIL import Image  # noqa: PLC0415
    with Image.open(pic) as im:
        ar = im.width / im.height
    avail_w, avail_h = Inches(12.4), Inches(4.75)
    w = avail_w; h = int(w / ar)
    if h > avail_h:
        h = avail_h; w = int(h * ar)
    slide.shapes.add_picture(str(pic), int((SLIDE_W - w) / 2), Inches(1.80), w, h)
    return slide


def slide_results(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Results Achieved So Far — Model Comparison")
    add_table(slide, RESULTS_HEADERS, RESULTS_ROWS, RESULTS_COLS,
              top=Inches(1.86), height=Inches(1.75),
              head_size=9.5, body_size=9.0)
    add_bullets(slide, RESULTS_NOTES, size=11.5, top=Inches(3.80),
                height=Inches(2.55), space_after=6)
    add_note(slide, SYNTHETIC_WARNING, top=Inches(6.52), size=9)
    return slide


def slide_calibration(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Uncertainty Calibration and the Ablation Study")
    add_bullets(slide, CALIBRATION, size=12.5, space_after=5,
                height=Inches(4.5))
    add_note(slide, SYNTHETIC_WARNING, top=Inches(6.52), size=9)
    return slide


def slide_prototype(prs, logos):
    slide = blank_slide(prs, logos)
    add_title(slide, "Prototype Walkthrough — “Iiris”")
    from PIL import Image  # noqa: PLC0415
    shots = [ASSETS / "app_dashboard.png", ASSETS / "app_simulator.png"]
    gap = Inches(0.35)
    each_w = int((SLIDE_W - 2 * MARGIN - gap) / 2)
    top = Inches(1.86)
    max_h = Inches(3.95)
    for i, (path, caption) in enumerate(zip(shots, PROTOTYPE_CAPTIONS)):
        with Image.open(path) as im:
            ar = im.width / im.height
        w = each_w; h = int(w / ar)
        if h > max_h:
            h = max_h; w = int(h * ar)
        left = MARGIN + i * (each_w + gap) + int((each_w - w) / 2)
        slide.shapes.add_picture(str(path), left, top, w, h)
        box = slide.shapes.add_textbox(MARGIN + i * (each_w + gap),
                                       top + max_h + Inches(0.08),
                                       each_w, Inches(0.5))
        tf = box.text_frame; tf.word_wrap = True
        para = tf.paragraphs[0]; para.alignment = PP_ALIGN.CENTER
        run = para.add_run(); run.text = caption
        run.font.size = Pt(10.5); run.font.name = FONT; run.font.color.rgb = GREY
    add_note(slide, "Live at http://localhost:5173 — the full loop (add a visit → twin "
                    "version increments → predictions recompute) can be demonstrated in "
                    "the review.", top=Inches(6.60), size=9.5)
    return slide


# ==========================================================================
def main() -> None:
    prs, logos, thankyou = load_template()

    slide_title(prs, logos)
    slide_contents(prs, logos)
    slide_bullets(prs, logos, "Introduction", INTRODUCTION, size=16)
    slide_bullets(prs, logos, "Domain & SDG Mapping", DOMAIN, size=16)
    slide_bullets(prs, logos, "Problem Statement", PROBLEM, size=16)
    slide_bullets(prs, logos, "Objectives", OBJECTIVES, size=16)
    slide_bullets(prs, logos, "Project Scope", SCOPE, size=15)

    # Literature Review and Base Paper are template slides that the template's own
    # Contents list omits; they are kept in the template's position, after Scope.
    slide_literature(prs, logos, LITERATURE[0:7])
    slide_literature(prs, logos, LITERATURE[7:14])
    slide_literature(prs, logos, LITERATURE[14:20])
    slide_base_paper(prs, logos)

    slide_bullets(prs, logos, "Source of Data Collection", DATA_SOURCES, size=13)
    slide_bullets(prs, logos, "Expected Outcomes", OUTCOMES, size=15)
    slide_bullets(prs, logos, "Tools & Technologies", TOOLS, size=12.5)

    # Methodology, then the slides that evidence it.
    slide_methodology(prs, logos)
    slide_architecture(prs, logos)
    slide_bullets(prs, logos, "Implementation Status — What Runs Today",
                  IMPLEMENTATION, size=13)
    slide_results(prs, logos)
    slide_calibration(prs, logos)
    slide_prototype(prs, logos)

    slide_gantt(prs, logos)
    slide_references(prs, logos, REFERENCES_1)
    slide_references(prs, logos, REFERENCES_2)
    slide_thankyou(prs, logos, thankyou)

    prs.save(str(OUT))
    print(f"Saved {OUT}  ({len(prs.slides._sldIdLst)} slides)")


if __name__ == "__main__":
    main()
