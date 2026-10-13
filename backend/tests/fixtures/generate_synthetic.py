"""Generate a SYNTHETIC longitudinal myopia cohort.

WHY THIS EXISTS
---------------
Real de-identified hospital data is not available yet. This generator produces a
plausible longitudinal cohort so the twin, the models, the simulator and the UI
can be built and demonstrated end to end today.

IT IS NOT REAL DATA. Every number here comes from a hand-written progression
equation, not from patients. Nothing measured on this cohort is a clinical
finding. Replace it with real data by following docs/DATA_ONBOARDING.md -- the
CSV column contract is identical, so no other code has to change.

The equation encodes directions that are broadly reported in the myopia
literature (younger age, parental myopia, more near work and less outdoor time
associate with faster progression) so that the pipeline has learnable signal and
the what-if simulator responds in a sensible direction. The magnitudes are
illustrative.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

TREATMENTS = ["none", "single_vision", "atropine", "ortho_k", "dims"]
# Multiplier applied to the annual progression rate. Illustrative values.
TREATMENT_EFFECT = {
    "none": 1.0,
    "single_vision": 1.0,
    "atropine": 0.55,
    "ortho_k": 0.60,
    "dims": 0.62,
}


def _clip(x: float, lo: float, hi: float) -> float:
    return float(min(max(x, lo), hi))


def simulate_patient(rng: np.random.Generator, idx: int, n_visits: int,
                     interval_months: int, start: date) -> list[dict]:
    age = float(rng.uniform(6.0, 13.0))
    sex = "male" if rng.random() < 0.5 else "female"
    parental = int(rng.choice([0, 1, 2], p=[0.45, 0.38, 0.17]))

    # Baseline refraction: a mix of emmetropic and already-myopic children.
    se = float(rng.normal(-0.75 - 0.45 * parental, 1.2))
    se = _clip(se, -6.0, 1.5)
    cornea = float(rng.normal(7.75, 0.25))
    al = 23.4 - 0.37 * se + float(rng.normal(0, 0.45))

    # Stable behavioural/ergonomic tendencies with per-visit drift.
    screen_base = _clip(rng.normal(4.2, 1.6), 0.5, 12.0)
    near_base = _clip(rng.normal(210, 70), 30, 600)
    outdoor_base = _clip(rng.normal(70, 40), 5, 300)
    sleep_base = _clip(rng.normal(8.2, 0.9), 5.0, 11.0)
    dist_base = _clip(rng.normal(31, 6), 15, 55)
    posture_base = _clip(rng.normal(0.65, 0.15), 0.1, 1.0)
    session_base = _clip(rng.normal(45, 18), 10, 180)

    treatment = "none"
    # Some children start myopia control partway through follow-up.
    switch_visit = int(rng.integers(1, n_visits)) if rng.random() < 0.35 else None
    switch_to = str(rng.choice(["atropine", "ortho_k", "dims"]))

    rows: list[dict] = []
    visit_date = start + timedelta(days=int(rng.integers(0, 300)))

    for v in range(n_visits):
        if switch_visit is not None and v == switch_visit:
            treatment = switch_to

        screen = _clip(screen_base + rng.normal(0, 0.7) + 0.10 * v, 0.0, 16.0)
        near = _clip(near_base + rng.normal(0, 30) + 6.0 * v, 0.0, 700.0)
        outdoor = _clip(outdoor_base + rng.normal(0, 18) - 2.0 * v, 0.0, 420.0)
        sleep = _clip(sleep_base + rng.normal(0, 0.4), 3.0, 12.0)
        dist = _clip(dist_base + rng.normal(0, 3), 12.0, 70.0)
        posture = _clip(posture_base + rng.normal(0, 0.07), 0.0, 1.0)
        session = _clip(session_base + rng.normal(0, 10) + 1.5 * v, 5.0, 240.0)

        # Visual acuity degrades mildly with uncorrected myopia (logMAR).
        va = _clip(0.02 + max(0.0, -se - 1.0) * 0.035 + rng.normal(0, 0.02), -0.1, 1.0)

        rows.append({
            "patient_key": f"SYN{idx:05d}",
            "visit_date": visit_date.isoformat(),
            "age": round(age, 2),
            "sex": sex,
            "parental_myopia": parental,
            "spherical_equivalent": round(se, 3),
            "axial_length": round(al, 3),
            "visual_acuity": round(va, 3),
            "corneal_curvature": round(cornea, 3),
            "treatment": treatment,
            "screen_time_hours": round(screen, 2),
            "near_work_min": round(near, 1),
            "outdoor_min": round(outdoor, 1),
            "sleep_hours": round(sleep, 2),
            "viewing_distance_cm": round(dist, 1),
            "posture_score": round(posture, 3),
            "continuous_session_min": round(session, 1),
            "source": "synthetic",
        })

        # ---- progression to the next visit -------------------------------
        years = interval_months / 12.0

        # Calibration target: mean annual SE change near -0.45 D/year, so the
        # cohort's progression distribution sits in the range reported for
        # school-age children rather than an implausible -1 D/year.
        # Age effect: progression is fastest in younger children and slows down.
        age_term = 0.42 * np.exp(-0.16 * (age - 6.0))
        # Heredity.
        hered_term = 0.10 * parental
        # Modifiable exposures (directions are literature-inspired, sizes illustrative).
        outdoor_term = -0.0018 * (outdoor - 70.0)
        near_term = 0.0005 * (near - 200.0)
        screen_term = 0.018 * (screen - 4.0)
        dist_term = -0.010 * (dist - 31.0)
        session_term = 0.0010 * (session - 45.0)
        posture_term = -0.08 * (posture - 0.65)
        # Already-myopic eyes tend to keep progressing.
        se_term = -0.03 * se

        annual = (0.05 + age_term + hered_term + outdoor_term + near_term
                  + screen_term + dist_term + session_term + posture_term + se_term)
        annual = max(annual, 0.0) * TREATMENT_EFFECT[treatment]
        annual += float(rng.normal(0, 0.12))          # between-visit biological noise

        d_se = -annual * years
        # Axial elongation is coupled to refractive change but not perfectly.
        d_al = 0.38 * (-d_se) + float(rng.normal(0, 0.035)) + 0.045 * years

        se = _clip(se + d_se, -14.0, 3.0)
        al = _clip(al + d_al, 20.5, 30.0)
        age += years
        visit_date += timedelta(days=int(interval_months * 30.44 + rng.integers(-20, 21)))

    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patients", type=int, default=600)
    ap.add_argument("--visits", type=int, default=8)
    ap.add_argument("--interval-months", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20260908)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1] / "data" / "synthetic_cohort.csv")
    # Simulates a real-world dataset where behaviour/ergonomics are only partly recorded.
    ap.add_argument("--missing-behaviour", type=float, default=0.12)
    ap.add_argument("--missing-ergonomics", type=float, default=0.22)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    rows: list[dict] = []
    for i in range(args.patients):
        rows.extend(simulate_patient(rng, i, args.visits, args.interval_months, date(2021, 1, 15)))

    behaviour_cols = ["screen_time_hours", "near_work_min", "outdoor_min", "sleep_hours"]
    ergo_cols = ["viewing_distance_cm", "posture_score", "continuous_session_min"]
    for r in rows:
        if rng.random() < args.missing_behaviour:
            for c in behaviour_cols:
                r[c] = ""
        if rng.random() < args.missing_ergonomics:
            for c in ergo_cols:
                r[c] = ""

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"SYNTHETIC data written: {args.out}")
    print(f"  patients={args.patients}  rows={len(rows)}  visits/patient={args.visits}")
    print("  NOT REAL PATIENT DATA -- see docs/DATA_ONBOARDING.md to swap in a real cohort.")


if __name__ == "__main__":
    main()
