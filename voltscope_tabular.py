"""Explicit-header CSV and XLSX data tables; no implicit physical conversions."""
import csv
import math
import io
from pathlib import Path
from voltscope_import_utils import decode_text, table_curve, metadata_json

UNITS = {'V','mV','A','mA','µA','uA','nA','s','Hz','Ohm','Ω','deg','rad','C','µC','F','A/cm2'}


def _table(path, title, values, kind):
    values = list(values)
    while values and not any(v is not None and str(v).strip() for v in values[0]):
        values.pop(0)
    if len(values) < 2:
        raise ValueError(f'{title}: expected a header and measurement rows.')
    width = max(len(row) for row in values)
    labels = [str(v).strip() if v is not None and str(v).strip() else f'Column {i + 1}'
              for i, v in enumerate(list(values[0]) + [None] * (width - len(values[0])))]
    metadata = {'FORMAT': kind, 'TITLE': title, 'TABLE_HEADER': metadata_json(list(values[0]))}
    start = 1
    # NIST-style export: series titles followed by a separate row of units.
    if len(values[1]) == width and all(v is None or str(v).strip() in UNITS for v in values[1]) and any(values[1]):
        labels = [f'{label} [{unit}]' if unit else label for label, unit in zip(labels, values[1])]
        start = 2
    rows = []
    for index, source in enumerate(values[start:], start + 1):
        if not any(v is not None and str(v).strip() for v in source):
            continue
        if len(source) != width:
            raise ValueError(f'{title}: column count mismatch at row {index}.')
        row = []
        for value in source:
            if value is None:
                row.append('')
            elif isinstance(value, bool):
                row.append(str(value))
            elif isinstance(value, (int,float)):
                row.append(value)
            elif isinstance(value, str):
                if value.startswith('='):
                    raise ValueError(f'{title}: formula cells are unsupported; save a values-only table.')
                try:
                    row.append(float(value.strip().replace(',', '.')))
                except ValueError:
                    row.append(value)
            else:
                row.append(str(value))
        rows.append(row)
    if not rows or not any(isinstance(v,(int,float)) and math.isfinite(v) for row in rows for v in row):
        raise ValueError(f'{title}: no numeric data rows.')
    metadata['UNIT_NOTE'] = 'Headers determine units; missing meanings/units remain unknown. No reference, area, or time-axis inference.'
    return table_curve(path, title, labels, rows, metadata)


def read_csv_table(path):
    text = decode_text(Path(path).read_bytes())
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
    except csv.Error as exc:
        raise ValueError('Could not identify a consistent CSV delimiter (comma, semicolon, or tab).') from exc
    rows = [row for row in csv.reader(io.StringIO(text), dialect=dialect) if any(v.strip() for v in row)]
    def numeric(value):
        try:
            float(value.strip().replace(',', '.'))
            return True
        except ValueError:
            return False
    if rows and len(rows[0]) >= 2 and all(not v.strip() or numeric(v) for v in rows[0]):
        # Legacy viewPAR exports are adjacent, headerless X/Y pairs. Never
        # discard the first measurement or assign assumed physical units.
        width = len(rows[0])
        if width % 2 or any(len(row) != width for row in rows):
            raise ValueError('Headerless CSV requires complete adjacent X/Y column pairs with consistent row widths.')
        curves = []
        from voltscope_data import Curve
        for pair in range(width//2):
            values = []
            for n, row in enumerate(rows, 1):
                x, y = row[2*pair:2*pair+2]
                if not x.strip() and not y.strip():
                    continue
                if not numeric(x) or not numeric(y):
                    raise ValueError(f'Headerless CSV pair {pair+1}, row {n}: incomplete or nonnumeric X/Y data.')
                values.append([float(x.replace(',', '.')),float(y.replace(',', '.')),n])
            if values:
                curves.append(Curve(str(path), f'{Path(path).stem} · pair {pair+1}',
                    ['X','Y','Source row'], ['unknown','unknown','1'], values,
                    {'FORMAT':'Headerless CSV pairs','STATUS':'Column meanings/units unknown. Use Assign column units before physical analysis.',
                     'DEFAULT_X':'X','DEFAULT_Y':'Y','SOURCE_COLUMNS':f'Columns {2*pair+1}, {2*pair+2}'}))
        if not curves:
            raise ValueError('Headerless CSV contains no complete numeric pairs.')
        return curves
    return [_table(path, Path(path).stem, rows, 'CSV table')]


def read_xlsx(path):
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise ValueError('XLSX requires openpyxl. Run python -m pip install -r requirements.txt') from exc
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        curves, empty = [], []
        for sheet in workbook:
            values = list(sheet.iter_rows(values_only=True))
            if not any(any(v is not None for v in row) for row in values):
                empty.append(sheet.title)
                continue
            curves.append(_table(path, sheet.title, values, 'XLSX table'))
        if not curves:
            raise ValueError('Workbook has no data tables.')
        for curve in curves:
            if empty:
                curve.metadata['STATUS'] = 'Empty sheets skipped: ' + ', '.join(empty)
        return curves
    finally:
        workbook.close()
