"""Preserve published subject linkage and annual visits; never infer identities from row order."""
from pathlib import Path
import numpy as np
import pandas as pd


def normalize(path: Path, sheet: str):
    df = pd.read_excel(path, sheet_name=sheet)
    expected = ['ID', 'Birth', 'Baseline' if sheet == 'GOAL' else 'baseline'] + [
        f'{n}{suffix} year' for n, suffix in [(1, 'st'), (2, 'nd'), (3, 'rd')] + ([] if sheet == 'GOAL' else [(4, 'th'), (5, 'th')])]
    if list(df.columns) != expected or df.ID.isna().any() or df.ID.duplicated().any():
        raise ValueError(f'Unreviewed subject/visit structure in {sheet}')
    if len(df) != {'GOAL': 1610, 'RELS': 2042}[sheet]:
        raise ValueError('Unexpected cohort size')
    rows = []
    for row in df.to_dict('records'):
        for year, column in enumerate(expected[2:]):
            se = row[column]
            rows.append({'patient_key': f'{sheet.lower()}:{row["ID"]}', 'visit_date': None,
                'followup_month': float(year * 12), 'spherical_equivalent': se,
                'axial_length': np.nan, 'age': np.nan, 'source': f'PLOS {sheet} 10.1371/journal.pmed.1002674',
                'treatment': None})
    # No invented AL, age, dates, exposure or treatment allocation. DOB is excluded.
    return pd.DataFrame(rows)
