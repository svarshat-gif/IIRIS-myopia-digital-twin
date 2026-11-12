"""Protect patient linkage, measured labels and source boundaries for trajectories."""
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.ml.features import ALL_FEATURES, build_feature_row
from app.ml.trajectory import build_pairs, patient_weights, source_partitions
from scripts.normalize_kinoshita import SOURCE_SHA256, build, normalize

BACKEND = Path(__file__).resolve().parents[1]
RAW_KINOSHITA = BACKEND / 'data/open/kinoshita/Dataset_Kinoshita_v7.xlsx'


def _visit(key, month, se, al, **metadata):
    return {'patient_key': key, 'visit_date': None, 'followup_month': float(month),
            'spherical_equivalent': se, 'axial_length': al, **metadata}


@pytest.fixture
def irregular_visits():
    return pd.DataFrame([
        _visit('patient:a', 0, -1.0, 24.0, age=9.0),
        _visit('patient:a', 4, -1.2, 24.1, age=9.3),
        _visit('patient:a', 13, -1.5, 24.3, age=10.1),
    ])


def test_kinoshita_reproducible_normalization_preserves_source_measurements(tmp_path):
    first = tmp_path / 'first.csv'
    second = tmp_path / 'second.csv'
    provenance = build(RAW_KINOSHITA, first)
    build(RAW_KINOSHITA, second)
    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(RAW_KINOSHITA.read_bytes()).hexdigest() == SOURCE_SHA256
    assert provenance['source_sha256'] == SOURCE_SHA256
    assert provenance['table_sha256'] == hashlib.sha256(first.read_bytes()).hexdigest()
    saved = json.loads(first.with_suffix('.provenance.json').read_text(encoding='utf-8'))
    assert saved['license'] == 'CC-BY-4.0'
    assert saved['allowed_targets'] == ['al']
    visits = pd.read_csv(first)
    assert len(visits) == 438
    assert visits.patient_key.nunique() == 73
    assert set(visits.eye) == {'R'}
    assert not visits.duplicated(['patient_key', 'followup_month']).any()
    assert visits.groupby('patient_key').size().eq(6).all()
    assert set(visits.followup_month) == {0, 3, 9, 15, 21, 27}
    patients = visits.drop_duplicates('patient_key')
    assert patients.treatment.value_counts().to_dict() == {'ortho_k_atropine': 38, 'ortho_k': 35}
    # This is a measured right-eye sequence, not the adjacent left-eye value or a formula average.
    patient = visits[visits.patient_key == 'kinoshita:ortho_k_atropine:1']
    assert patient.axial_length.tolist() == [25.54, 25.52, 25.56, 25.35, 25.71, 25.68]
    assert patient.source_al_cell.tolist() == ['I5', 'K5', 'N5', 'Q5', 'T5', 'W5']
    assert patient.loc[patient.followup_month == 0, 'spherical_equivalent'].item() == -2.25


def test_kinoshita_does_not_fabricate_followup_se_age_or_atropine_start():
    visits = normalize(RAW_KINOSHITA)
    later = visits[visits.followup_month > 0]
    assert later.spherical_equivalent.isna().all()
    assert later.age.isna().all()
    assert visits[visits.followup_month == 0].age.notna().all()
    assert visits.age_at_enrollment_years.notna().all()
    assert visits.groupby('patient_key').age_at_enrollment_years.nunique().eq(1).all()
    assert visits.visit_date.isna().all()
    assert visits[visits.followup_month == 0].atropine_started.eq(False).all()
    combo_after_start = visits[(visits.treatment == 'ortho_k_atropine') & (visits.followup_month >= 3)]
    assert combo_after_start.atropine_started.eq(True).all()
    assert visits[visits.treatment == 'ortho_k'].atropine_started.eq(False).all()


def test_kinoshita_rejects_changed_raw_file_before_parsing(tmp_path):
    changed = tmp_path / 'changed.xlsx'
    changed.write_bytes(RAW_KINOSHITA.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='source checksum'):
        normalize(changed)


def test_pairs_use_every_actual_future_interval_without_generating_monthly_labels(irregular_visits):
    pairs = build_pairs(irregular_visits)
    assert len(pairs) == 3
    assert pairs.horizon_months.tolist() == [4.0, 13.0, 9.0]
    assert pairs.n_visits.tolist() == [1.0, 1.0, 2.0]
    assert pairs.y_se.tolist() == [-1.2, -1.5, -1.5]
    assert pairs.y_al.tolist() == [24.1, 24.3, 24.3]
    assert pairs.se.tolist() == [-1.0, -1.0, -1.2]
    assert pairs.al.tolist() == [24.0, 24.0, 24.1]


def test_pairs_preserve_measured_calendar_intervals():
    visits = pd.DataFrame([
        _visit('calendar:a', 0, -1.0, 24.0, visit_date_override=date(2020, 1, 1)),
        _visit('calendar:a', 0, -1.5, 24.2, visit_date_override=date(2020, 6, 2)),
    ])
    visits['visit_date'] = visits.pop('visit_date_override')
    visits['followup_month'] = np.nan
    pairs = build_pairs(visits)
    assert pairs.horizon_months.item() == pytest.approx(153 / 30.4375)
    assert pairs.y_se.item() == -1.5


def test_future_measurements_treatment_and_metadata_cannot_change_index_features(irregular_visits):
    original = irregular_visits.assign(sex=None, parental_myopia=np.nan, treatment='none')
    original.loc[0, 'sex'] = 'F'
    changed = original.copy()
    changed.loc[1:, 'spherical_equivalent'] = [-10.0, -20.0]
    changed.loc[1:, 'axial_length'] = [30.0, 34.0]
    changed.loc[1:, 'age'] = [30.0, 40.0]
    changed.loc[1:, 'sex'] = 'M'
    changed.loc[1:, 'parental_myopia'] = 2
    changed.loc[1:, 'treatment'] = 'ortho_k_atropine'
    changed.loc[1:, 'screen_time_hours'] = 20.0
    before = build_pairs(original).query('n_visits == 1').reset_index(drop=True)
    after = build_pairs(changed).query('n_visits == 1').reset_index(drop=True)
    pd.testing.assert_frame_equal(before[ALL_FEATURES + ['horizon_months']],
                                  after[ALL_FEATURES + ['horizon_months']])
    assert after.y_se.tolist() == [-10.0, -20.0]
    assert after.y_al.tolist() == [30.0, 34.0]
    assert after.sex_male.eq(0).all()
    assert after.parental_myopia.isna().all()


def test_kinoshita_pairs_exclude_pre_atropine_index_and_have_no_se_targets():
    key = 'kinoshita:ortho_k_atropine:fixture'
    visits = pd.DataFrame([
        _visit(key, 0, -2.0, 24.0, age=9.0, treatment='ortho_k_atropine'),
        _visit(key, 3, None, 24.1, treatment='ortho_k_atropine'),
        _visit(key, 9, None, 24.2, treatment='ortho_k_atropine'),
        _visit(key, 27, None, 24.5, treatment='ortho_k_atropine'),
    ])
    pairs = build_pairs(visits)
    assert len(pairs) == 3
    assert pairs.months_since_baseline.tolist() == [3.0, 3.0, 9.0]
    assert pairs.horizon_months.tolist() == [6.0, 24.0, 18.0]
    assert pairs.y_al.tolist() == [24.2, 24.5, 24.5]
    assert pairs.y_se.isna().all()
    assert pairs.treatment_atropine.eq(1).all()
    assert pairs.treatment_optical.eq(1).all()


def test_source_partitions_keep_whole_patients_and_are_stable_under_group_order():
    rows = [_visit(f'kinoshita:ortho_k:{patient}', month, None, 24 + month * .01,
                   treatment='ortho_k')
            for patient in range(20) for month in (0, 3, 9, 27)]
    visits = pd.DataFrame(rows)
    partitions = source_partitions(visits, 'kinoshita')
    memberships = [set(frame.patient_key) for frame in partitions]
    assert [len(group) for group in memberships] == [12, 4, 4]
    assert set.union(*memberships) == set(visits.patient_key)
    assert not memberships[0] & memberships[1]
    assert not memberships[0] & memberships[2]
    assert not memberships[1] & memberships[2]
    for frame in partitions:
        assert frame.groupby('patient_key').size().eq(3).all()
    reversed_groups = pd.concat([group for _, group in visits.groupby('patient_key', sort=False)][::-1])
    assert [set(frame.patient_key) for frame in source_partitions(reversed_groups, 'kinoshita')] == memberships


def test_pair_weights_give_equal_total_weight_to_each_patient():
    frame = pd.DataFrame({'patient_key': ['short'] + ['long'] * 10})
    weights = patient_weights(frame)
    totals = pd.Series(weights).groupby(frame.patient_key).sum()
    assert totals['short'] == pytest.approx(1.0)
    assert totals['long'] == pytest.approx(1.0)


@pytest.mark.parametrize('treatment,atropine,optical', [
    ('ortho_k_atropine', 1.0, 1.0), ('ORTHO_K_ATROPINE', 1.0, 1.0),
    ('ortho_k', 0.0, 1.0), ('atropine', 1.0, 0.0), ('none', 0.0, 0.0),
])
def test_combination_treatment_retains_both_feature_flags(treatment, atropine, optical):
    row = build_feature_row([_visit('patient:a', 0, -1.0, 24.0, treatment=treatment)])
    assert row['treatment_atropine'] == atropine
    assert row['treatment_optical'] == optical
