"""Verify licensed research inputs and build tables with explicit, separate endpoints."""
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.normalize_longitudinal import normalize
from scripts.normalize_kinoshita import build as build_kinoshita

ROOT = Path(__file__).resolve().parents[1]


def build(source=ROOT / 'data/open', out=ROOT / 'data/research'):
    sources = json.loads((source / 'research_sources.json').read_text(encoding='utf-8'))
    expected = {'olsm': 'GPL-3', 'aier_seri': 'CC0-1.0', 'miopia': 'CC-BY-NC-4.0',
                'goal_rels': 'CC-BY-4.0', 'dryad_3year': 'CC0-1.0', 'kinoshita': 'CC-BY-4.0'}
    for name, license_id in expected.items():
        record = sources[name]
        if record['license'] != license_id or record['data_is_synthetic'] is not False:
            raise ValueError(f'Unreviewed license or synthetic source: {name}')
        for filename, checksum in record['files'].items():
            if Path(filename).name != filename:
                raise ValueError('Invalid source filename')
            if hashlib.sha256((source / name / filename).read_bytes()).hexdigest() != checksum:
                raise ValueError(f'Research source checksum mismatch: {name}/{filename}')
    archive = (source / 'olsm/aplore3_0.9.tar.gz').read_bytes()
    if hashlib.md5(archive).hexdigest() != sources['olsm']['repository_md5']:
        raise ValueError('CRAN repository checksum mismatch')
    out.mkdir(parents=True, exist_ok=True)
    olsm = pd.read_csv(source / 'olsm/myopia.csv')
    if len(olsm) != 618 or olsm.id.duplicated().any():
        raise ValueError('Unreviewed OLSM subject structure')
    for c in ('myopic', 'mommy', 'dadmy'):
        if not olsm[c].isin(['No', 'Yes']).all():
            raise ValueError(f'Unreviewed category coding: {c}')
        olsm[c] = olsm[c].map({'No': 0, 'Yes': 1})
    if not olsm.gender.isin(['Male', 'Female']).all():
        raise ValueError('Unreviewed gender coding')
    olsm.gender = olsm.gender.map({'Male': 0, 'Female': 1})
    olsm['patient_key'] = 'olsm:' + olsm.id.astype(str)
    olsm.to_csv(out / 'olsm_onset.csv', index=False, lineterminator='\n')
    aier = pd.read_excel(source / 'aier_seri/S3 Data.xlsx', sheet_name='shared data')
    if len(aier) != 431 or aier.id.duplicated().any():
        raise ValueError('Unreviewed Aier-SERI subject structure')
    # Preserve eye suffixes verbatim: the supplied codebook has a side ambiguity.
    aier['patient_key'] = 'aier:' + aier.id.astype(str)
    aier.to_csv(out / 'aier_baseline.csv', index=False, lineterminator='\n')
    x = pd.read_csv(source / 'miopia/X_train.csv')
    y = pd.read_csv(source / 'miopia/Y_train.csv')
    test = pd.read_csv(source / 'miopia/X_test.csv')
    if len(x) != 132 or len(y) != len(x) or len(test) != 24:
        raise ValueError('Unreviewed Miopia file alignment')
    # A row key is not evidence of subject identity or longitudinal linkage.
    train = pd.concat([x, y.add_prefix('label_')], axis=1)
    train['row_key'] = [f'miopia:train:{i}' for i in range(len(train))]
    test['row_key'] = [f'miopia:test:{i}' for i in range(len(test))]
    pd.concat([train, test], ignore_index=True).to_csv(out / 'miopia_research.csv', index=False, lineterminator='\n')
    catalog = []
    for name, title, rows, patients, role, limitations in [
        ('olsm', 'OLSM / aplore3 MYOPIA', 618, 618, 'Five-year onset model training',
         ['Baseline predictors and five-year binary onset only; no serial SE/AL.',
          'Weekly activities are proxies; sports/outdoor is not pure outdoor exposure.',
          'Ages 5-9, initially nonmyopic; no causal intervention estimates.']),
        ('aier_seri', 'Aier-SERI adult high-myopia baseline', 431, 431, 'Baseline reference dataset',
         ['Adults aged 29-78; no future targets, exposures or repeated visits.',
          'Eye-side suffix/codebook ambiguity is preserved; not used for forecast validation.']),
        ('miopia', 'Miopia medical-student research', 156, None, 'Noncommercial research table',
         ['132 labeled plus 24 unlabeled rows; unique subjects/linkage unverified.',
          'No future SE/AL targets; no onset/progression training.',
          'CC BY-NC 4.0: noncommercial use only; original scales/protocol need review.'])]:
        table = out / {'olsm': 'olsm_onset.csv', 'aier_seri': 'aier_baseline.csv', 'miopia': 'miopia_research.csv'}[name]
        catalog.append({'id': name, 'name': title, 'rows': rows, 'n_patients': patients,
                        'role': role, 'license': sources[name]['license'],
                        'source_url': sources[name]['source_url'], 'data_is_synthetic': False,
                        'table_sha256': hashlib.sha256(table.read_bytes()).hexdigest(),
                        'limitations': limitations})
    for sheet in ('GOAL', 'RELS'):
        visits = normalize(source / 'goal_rels/goal_rels.xlsx', sheet)
        table = out / f'{sheet.lower()}_visits.csv'
        visits.to_csv(table, index=False, lineterminator='\n')
        catalog.append({'id': sheet.lower(), 'name': f'PLOS {sheet} annual refraction cohort',
            'rows': len(visits), 'n_patients': visits.patient_key.nunique(), 'n_visits': int(visits.spherical_equivalent.notna().sum()),
            'role': '12-month SE/progression model development' if sheet == 'GOAL' else 'Study-held-out SE/progression evaluation',
            'license': sources['goal_rels']['license'], 'source_url': sources['goal_rels']['source_url'],
            'data_is_synthetic': False, 'table_sha256': hashlib.sha256(table.read_bytes()).hexdigest(),
            'limitations': ['Annual cycloplegic right-eye SE only; no AL or exposure/treatment allocation in released workbook.',
                'Annual labels mapped to nominal scheduled months; exact examination dates and age are unavailable.',
                'DOB is excluded from normalized model tables and predictors; missing SE stays missing.',
                'PLOS reports GOAL and RELS as independent cohorts; overlap with the separately sourced DIMS cohort is not verifiable from these files.']})
    catalog.append({'id': 'dryad_3year', 'name': 'Dryad / Zenodo Jinshan three-year reference',
        'rows': 2024, 'n_patients': None, 'role': 'Unlinked research measurements; excluded from longitudinal training',
        'license': 'CC0-1.0', 'source_url': 'https://zenodo.org/records/4987818', 'data_is_synthetic': False,
        'limitations': ['Original workbook matches Dryad SHA256 and Zenodo MD5; no subject IDs are published.',
            'Birth/examination fields are years; gender/birth-year combinations cannot establish identity.',
            'Slash/negative placeholders and non-cycloplegic measurements require careful handling; no row-order linkage.']})
    kinoshita = build_kinoshita(source / 'kinoshita/Dataset_Kinoshita_v7.xlsx',
                              out / 'kinoshita_visits.csv')
    catalog.append({**kinoshita,
        'role': 'Selectable-horizon axial-length development; right-eye patient-grouped evaluation',
        'limitations': kinoshita['limitations'] + [
            'Forecast pairs start at enrollment month 3 or later, after OK stabilization and atropine initiation.']})
    report = {'datasets': catalog, 'excluded': [
        {'id': 'human_lifestyle', 'reason': 'Explicitly synthetic and no ocular outcomes'},
        {'id': 'data3_kaggle', 'reason': 'Unknown license/origin and no verified patient linkage'},
        {'id': 'axial_prediction', 'reason': 'Unresolved license; static KH/KV/AL only'},
        {'id': 'shandong_habits', 'reason': 'Public 126375-row cross-sectional supplement inspected; no longitudinal outcome/subject linkage and CC BY-NC-ND terms; no forecasting training'}],
        'note': 'These datasets have separate roles. No cross-cohort patient joins or invented follow-up visits.'}
    (out / 'catalog.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
