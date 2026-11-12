"""Licensed source integration and independent onset endpoint contracts."""
import shutil

import pandas as pd
import pytest

from app.ml import onset, registry
from scripts.build_research_datasets import build, ROOT


@pytest.fixture(scope='module', autouse=True)
def prepared_research_data(tmp_path_factory):
    build()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(onset, 'MODEL_PATH', tmp_path_factory.mktemp('onset') / 'model.joblib')
        onset.train()
        yield
    onset.load.cache_clear()


def measured_subject():
    row = pd.read_csv(ROOT / 'data/research/olsm_onset.csv').iloc[1]
    return {c: float(row[c]) for c in onset.CLINICAL + onset.ACTIVITY}


def test_real_sources_are_separate_and_missing_stays_missing():
    c = onset.catalog()
    assert {x['id'] for x in c['datasets']} == {
        'olsm', 'aier_seri', 'miopia', 'goal', 'rels', 'dryad_3year', 'kinoshita'}
    assert {x['id']: x['rows'] for x in c['datasets']} == {
        'olsm': 618, 'aier_seri': 431, 'miopia': 156,
        'goal': 6440, 'rels': 12252, 'dryad_3year': 2024, 'kinoshita': 438}
    assert all(x['data_is_synthetic'] is False for x in c['datasets'])
    assert next(x for x in c['datasets'] if x['id'] == 'miopia')['n_patients'] is None
    aier = pd.read_csv(ROOT / 'data/research/aier_baseline.csv')
    assert aier.age.isna().sum() == 2
    assert len(aier) == aier.patient_key.nunique()
    # GOAL expands only 12-month SE training; DIMS remains the AL/6-month cohort.
    provenance = registry.load_bundle()['provenance']
    assert provenance['n_patients'] == 1630  # DIMS 20 + GOAL 1,610
    assert provenance['per_source']['Zenodo DIMS 36-month (18166476)']['n_patients'] == 20
    assert [x['id'] for x in provenance['additional_sources']] == ['goal']
    assert registry.load_bundle()['supported_scenario_inputs'] == []


def test_modified_source_is_rejected_before_normalization(tmp_path):
    source = tmp_path / 'open'
    shutil.copytree(ROOT / 'data/open', source)
    (source / 'olsm/myopia.csv').write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        build(source=source, out=tmp_path / 'out')


def test_onset_training_has_real_provenance_and_independent_evaluation():
    m = onset.metadata()
    assert m['n_patients'] == 618 and m['n_positive'] == 81
    assert m['split'] == {'train_patients': 370, 'calibration_patients': 124, 'test_patients': 124}
    assert m['split_positive']['test'] == 16
    assert m['data_is_synthetic'] is False and m['source']['license'] == 'GPL-3'
    for metrics in m['metrics'].values():
        assert 0 <= metrics['roc_auc'] <= 1 and 0 <= metrics['brier'] <= 1
        assert metrics['bootstrap_95ci']['roc_auc'][0] <= metrics['roc_auc'] <= metrics['bootstrap_95ci']['roc_auc'][1]
        assert sum(map(sum, metrics['confusion_matrix'])) == 124
        assert metrics['decision_threshold'] == .5
        assert metrics['prevalence_baseline']['sensitivity'] == 0
        assert metrics['model_selection']['selected'] == 'fixed_hgb_incumbent'


def test_onset_uses_measured_activity_or_clinical_model_without_filling():
    row = measured_subject()
    full = onset.predict(row)
    assert full['model'] == 'clinical_activity' and full['horizon_years'] == 5
    row['sporthr'] = None
    partial = onset.predict(row)
    assert partial['model'] == 'clinical' and row['sporthr'] is None
    assert partial['individual_probability_interval'] is None
    assert 'not a' in partial['disclaimer'].lower()


def test_research_api_auth_domain_and_catalog(client, admin_headers):
    row = measured_subject()
    for c in ('gender', 'mommy', 'dadmy'):
        row[c] = int(row[c])
    route = '/api/v1/research/onset/predict'
    assert client.post(route, json=row).status_code == 401
    response = client.post(route, json=row, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()['horizon_years'] == 5 and 'horizons' not in response.json()
    for invalid in ({'age': 18}, {'spheq': -4}, {'sporthr': -1}, {'patient_id': 'arbitrary'}):
        assert client.post(route, json={**row, **invalid}, headers=admin_headers).status_code == 422
    card = client.get('/api/v1/meta/model').json()
    assert card['metrics']['n_patients'] == 1630
    assert card['provenance']['per_source']['Zenodo DIMS 36-month (18166476)']['n_patients'] == 20
    assert card['onset_model']['n_patients'] == 618
    assert len(client.get('/api/v1/meta/datasets').json()['datasets']) == 7


def test_onset_training_refuses_changed_table(tmp_path):
    original = ROOT / 'data/research'
    shutil.copyfile(original / 'catalog.json', tmp_path / 'catalog.json')
    data = tmp_path / 'olsm_onset.csv'
    data.write_text('generated substitute', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        onset.train(data=data, out=tmp_path / 'bad.joblib')
