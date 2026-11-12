"""Normalize licensed Kinoshita AL measurements, retaining original nominal visit times.

The public workbook contains serial axial lengths but enrollment refraction only.
SE is therefore missing at every follow-up and cannot be used as a target.
"""
import argparse
import hashlib
import json
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = '423771baddd91a25356603c750b78dc45b8d6fdb3c0b18788eb21a72d6e011b5'
SOURCE_URL = 'https://data.mendeley.com/datasets/y58rh8bfkv/7'
DOWNLOAD_URL = ('https://data.mendeley.com/public-files/datasets/y58rh8bfkv/files/'
                'a729b5cd-9ec9-460c-90ac-441bc83956f1/file_downloaded')
VISITS = [('I', 0), ('K', 3), ('N', 9), ('Q', 15), ('T', 21), ('W', 27)]
LIMITATIONS = [
    'Enrollment SE only; follow-up SE is missing and no SE target is permitted.',
    'Study baseline is enrollment month 3, after three months of OK stabilization.',
    'Atropine starts at enrollment month 3 in the combination arm; month 0 is pre-atropine.',
    'Months are nominal workbook labels; exact follow-up examination dates are unavailable.',
    'Age is recorded only at enrollment; no later age is fabricated.',
    'Right eye only; Study ID is preserved with treatment-group namespace.',
    'Completers only: 73 Japanese children aged 8-12 at enrollment.',
    'Treatments are orthokeratology or orthokeratology plus 0.01% atropine; no untreated control.',
]


def normalize(path: Path) -> pd.DataFrame:
    """Return source-faithful right-eye visits after verifying the immutable raw file."""
    if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unreviewed Kinoshita source checksum')
    book = openpyxl.load_workbook(path, data_only=False)
    if book.sheetnames != ['OK and 0.01% atropine']:
        raise ValueError('Unreviewed Kinoshita workbook sheet structure')
    sheet = book.active
    if (sheet.max_row, sheet.max_column) != (154, 51):
        raise ValueError('Unreviewed Kinoshita dimensions')
    for header_row in (3, 83):
        expected = {'A': 'Study ID', 'C': 'Age', 'D': 'Sex',
                    'E': 'Spherical equivalent refraction (D)', 'H': 'Eye',
                    'I': 'Axial length (mm)'}
        if any(sheet[f'{col}{header_row}'].value != value for col, value in expected.items()):
            raise ValueError('Unreviewed Kinoshita column definitions')
        for col, month in VISITS:
            expected_month = f'{month} month' if month == 0 else f'{month} months'
            if sheet[f'{col}{header_row + 1}'].value != expected_month:
                raise ValueError('Unreviewed Kinoshita nominal visit times')
    rows = []
    groups = [('ortho_k_atropine', 5, 80, 38), ('ortho_k', 85, 154, 35)]
    for treatment, first, last, count in groups:
        ids = []
        for r in range(first, last + 1, 2):
            sid = sheet[f'A{r}'].value
            if not isinstance(sid, (int, float)) or int(sid) != sid:
                raise ValueError('Invalid original Study ID')
            ids.append(int(sid))
            if [sheet[f'H{r + k}'].value for k in (0, 1)] != ['R', 'L']:
                raise ValueError('Unreviewed eye allocation')
            age, sex, se = (sheet[f'{col}{r}'].value for col in ('C', 'D', 'E'))
            if (not isinstance(age, (int, float)) or not 8 <= age < 13
                    or sex not in ('M', 'F') or not isinstance(se, (int, float))
                    or not -6 <= se <= -1):
                raise ValueError('Invalid Kinoshita enrollment values')
            for col, month in VISITS:
                al = sheet[f'{col}{r}'].value
                if not isinstance(al, (int, float)) or not 18 <= al <= 30:
                    raise ValueError(f'Invalid measured AL in {col}{r}')
                rows.append({'patient_key': f'kinoshita:{treatment}:{int(sid)}',
                    'visit_date': None, 'followup_month': float(month),
                    'spherical_equivalent': float(se) if month == 0 else None,
                    'axial_length': float(al), 'age': float(age) if month == 0 else None,
                    'age_at_enrollment_years': float(age), 'sex': sex,
                    'eye': 'R', 'source': 'Kinoshita 2020 10.17632/y58rh8bfkv.7',
                    'treatment': treatment,
                    'atropine_started': treatment == 'ortho_k_atropine' and month >= 3,
                    'source_row': r, 'source_al_cell': f'{col}{r}'})
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError('Unreviewed Kinoshita patient allocation')
    result = pd.DataFrame(rows)
    if result.patient_key.nunique() != 73 or len(result) != 438:
        raise ValueError('Unreviewed Kinoshita cohort size')
    if result.duplicated(['patient_key', 'followup_month']).any():
        raise ValueError('Duplicate Kinoshita patient visit')
    if result.loc[result.followup_month != 0, ['age', 'spherical_equivalent']].notna().any().any():
        raise ValueError('Invented Kinoshita follow-up SE or age')
    return result


def build(source: Path = ROOT / 'data/open/kinoshita/Dataset_Kinoshita_v7.xlsx',
          output: Path = ROOT / 'data/research/kinoshita_visits.csv') -> dict:
    visits = normalize(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    visits.to_csv(output, index=False, lineterminator='\n')
    provenance = {'id': 'kinoshita', 'name': 'Kinoshita 2020 orthokeratology trial',
        'source_url': SOURCE_URL, 'download_url': DOWNLOAD_URL,
        'doi': '10.17632/y58rh8bfkv.7', 'license': 'CC-BY-4.0',
        'data_is_synthetic': False, 'allowed_targets': ['al'],
        'source_sha256': SOURCE_SHA256,
        'table_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'normalized_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'table': output.name, 'rows': len(visits), 'n_patients': 73,
        'n_visits': len(visits), 'eye': 'right',
        'followup_months': [m for _, m in VISITS],
        'trial_baseline_enrollment_month': 3,
        'age_policy': 'Only original enrollment age is populated in age. The explicitly named age_at_enrollment_years is a repeated baseline covariate, not follow-up age.',
        'se_policy': 'Only original enrollment SE is populated; no follow-up SE labels.',
        'limitations': LIMITATIONS,
        'extractor': 'scripts/normalize_kinoshita.py',
        'attribution': 'Kinoshita N et al. (2020), Mendeley Data V7, doi:10.17632/y58rh8bfkv.7; Scientific Reports 10:12750, doi:10.1038/s41598-020-69710-8.'}
    output.with_suffix('.provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/open/kinoshita/Dataset_Kinoshita_v7.xlsx')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/research/kinoshita_visits.csv')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))
