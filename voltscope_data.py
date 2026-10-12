"""Gamry DTA and Ivium IDF/IDS desktop viewer. UI-independent parsing and export."""
import csv
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Curve:
    source: str
    name: str
    columns: list
    units: list
    rows: list
    metadata: dict


def number(value):
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def read_dta(path):
    data = Path(path).read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('cp1252')
    lines = text.splitlines()
    metadata, curves = {}, []
    i = 0
    while i < len(lines):
        fields = lines[i].strip().split('\t')
        if len(fields) >= 2 and fields[1] == 'TABLE':
            name = fields[0]
            if i + 2 >= len(lines):
                raise ValueError(f'Incomplete table {name}')
            columns = lines[i + 1].strip().split('\t')
            units = lines[i + 2].strip().split('\t')
            if len(columns) != len(units):
                raise ValueError(f'Column/unit mismatch in {name}')
            rows = []
            i += 3
            while i < len(lines):
                row = lines[i].strip().split('\t')
                if not lines[i].strip():
                    i += 1
                    continue
                if number(row[0]) is None:
                    break
                if len(row) != len(columns):
                    raise ValueError(f'Malformed row in {name}, line {i + 1}')
                rows.append([number(v) if number(v) is not None else v for v in row])
                i += 1
            if rows:
                curves.append(Curve(str(path), name, columns, units, rows, metadata))
            continue
        if len(fields) >= 3:
            metadata[fields[0]] = fields[2]
        elif len(fields) == 2:
            metadata[fields[0]] = fields[1]
        i += 1
    if not curves:
        raise ValueError('No numeric data tables found in this DTA file.')
    return curves


def read_ivium(path):
    """Read embedded ASCII primary_data blocks in Ivium IDF/IDS containers.

    Column meanings are mapped only for the CV/sweep and CA layouts checked
    against the supplied examples. Other methods retain generic column names.
    """
    data = Path(path).read_bytes()
    marker = re.compile(rb'primary_data[ \t]*\r(?:\n|\x00)(\d+)[ \t]*\r\n(\d+)[ \t]*\r\n')
    curves = []
    for block, match in enumerate(marker.finditer(data), 1):
        width, count = map(int, match.groups())
        if not 1 <= width <= 100 or not 0 <= count <= 10_000_000:
            raise ValueError(f'Invalid Ivium table dimensions in block {block}')
        # Every scan has its own QR/settings section. Do not carry metadata
        # from a prior scan into a new scan.
        start = data.rfind(b'QR=', 0, match.start())
        prefix = data[max(start, 0):match.start()].decode('cp1252', errors='replace')
        metadata = {}
        for line in prefix.split('\r\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.split('\x00')[-1].strip()
                if key and all(ch.isprintable() for ch in key):
                    metadata[key] = value.strip()
        method = metadata.get('Method', '')
        technique = metadata.get('Technique', '')
        is_cv = method in ('CyclicVoltammetry', 'LinearSweep')
        is_ca = method == 'Transients' and technique == 'ChronoAmperometry'
        columns = ['Vset', 'Im', 'Vf'] if is_cv and width == 3 else ['T', 'Im', 'Vf'] if is_ca and width == 3 else [f'Column{j+1}' for j in range(width)]
        units = ['V vs. Ref.', 'A', 'V vs. Ref.'] if is_cv and width == 3 else ['s', 'A', 'V vs. Ref.'] if is_ca and width == 3 else ['unknown'] * width
        rows, offset = [], match.end()
        for row_index in range(count):
            end = data.find(b'\r\n', offset)
            if end < 0:
                raise ValueError(f'Truncated Ivium block {block}, row {row_index+1}')
            fields = data[offset:end].decode('ascii', errors='replace').split()
            values = [number(v) for v in fields]
            if len(values) != width or any(v is None for v in values):
                raise ValueError(f'Malformed Ivium block {block}, row {row_index+1}')
            rows.append(values)
            offset = end + 2
        metadata['FORMAT'] = 'Ivium'
        metadata['TAG'] = 'CV' if is_cv else 'CHRONOA' if is_ca else method
        metadata['TITLE'] = metadata.get('Title', '')
        metadata['PSTAT'] = metadata.get('serialnumber', '')
        metadata['DATE'] = metadata.get('starttime', '')
        metadata['AREA'] = metadata.get('Data Options.Area', '')
        metadata['SCANRATE'] = metadata.get('Scanrate', '')
        report = metadata.get('Report.Process data', '')
        metadata['STATUS'] = next((v.split(':', 1)[1].strip() for v in report.split('\x1c\x1e') if v.startswith('endcondition:')), '')
        container = Path(path).suffix.lower() == '.ids' and not metadata.get('starttime') and all(v == 0 for row in rows for v in row)
        metadata['CONTAINER'] = container
        if container:
            columns, units = [f'Column{j+1}' for j in range(width)], ['unknown'] * width
        qr = metadata.get('QR', '').split(',')
        label = qr[18] if len(qr) > 18 else f'Scan {block}'
        name = f'{block}: {label}' + (' (container table)' if container else '')
        if rows:
            curves.append(Curve(str(path), name, columns, units, rows, metadata))
    if not curves:
        raise ValueError('No supported Ivium primary_data blocks found.')
    return curves


def read_corrware(path):
    """Read CORRW ASCII tables using explicit column headers and row counts."""
    data = Path(path).read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('cp1252')
    lines = text.splitlines()
    if not lines or lines[0].strip() != 'CORRW ASCII':
        raise ValueError('Not a Corrware CORRW ASCII file.')
    try:
        end = next(i for i, line in enumerate(lines) if line.strip() == 'End Comments')
    except StopIteration:
        raise ValueError('Corrware file has no End Comments marker.') from None
    metadata = {'FORMAT': 'Corrware'}
    header = None
    for line in lines[1:end]:
        stripped = line.strip()
        if ':' in stripped:
            key, value = stripped.split(':', 1)
            metadata[key.strip()] = value.strip()
        tokens = stripped.split('\t')
        if len(tokens) > 1 and all(re.fullmatch(r'[^()]+\([^()]+\)', token.strip()) for token in tokens):
            header = [token.strip() for token in tokens]
    if header is None:
        raise ValueError('Corrware file has no supported column/unit header.')
    columns, units = [], []
    mappings = {('E', 'Volts'): ('Vf', 'V'), ('I', 'A/cm2'): ('J', 'A/cm2'),
                ('I', 'A/cm^2'): ('J', 'A/cm2'), ('I', 'A'): ('Im', 'A'),
                ('T', 'Seconds'): ('T', 's')}
    for token in header:
        label, unit = re.fullmatch(r'([^()]+)\(([^()]+)\)', token).groups()
        col, mapped_unit = mappings.get((label.strip(), unit.strip()), (label.strip(), unit.strip()))
        columns.append(col)
        units.append(mapped_unit)
    if len(set(columns)) != len(columns):
        raise ValueError('Duplicate Corrware column labels are unsupported.')
    rows = []
    for index in range(end + 1, len(lines)):
        if not lines[index].strip():
            continue
        fields = lines[index].split()
        row = [number(v) for v in fields]
        if len(row) != len(columns) or any(v is None for v in row):
            raise ValueError(f'Malformed Corrware data at line {index + 1}')
        rows.append(row)
    try:
        declared = int(metadata['Data Points'])
    except (KeyError, ValueError):
        raise ValueError('Missing or invalid Corrware Data Points count.') from None
    if declared != len(rows):
        raise ValueError(f'Corrware row count mismatch: declared {declared}, read {len(rows)}.')
    if not rows:
        raise ValueError('Corrware file contains no data points.')
    experiment = metadata.get('Begin Experiment', '').split('\t')[0]
    if not experiment:
        experiment = lines[2].strip().split('\t')[0] if len(lines) > 2 else 'Unknown'
    metadata['EXPERIMENT'] = experiment
    metadata['TAG'] = {'Cyclic Voltammogram': 'CV', 'Potentiostatic': 'CHRONOA', 'Galvanostatic': 'CHRONOP'}.get(experiment, experiment)
    metadata['TITLE'] = Path(path).stem
    metadata['PSTAT'] = metadata.get('Pstat Title', '')
    stamp = metadata.get('Date', '')
    date, _, clock = stamp.partition('Time:')
    metadata['DATE'], metadata['TIME'] = date.strip(), clock.strip()
    metadata['AREA'] = metadata.get('Surface Area', '')
    metadata['SCANRATE'] = metadata.get('Scan Rate', '')
    metadata['SOURCE_COLUMNS'] = ' | '.join(header)
    return [Curve(str(path), experiment, columns, units, rows, metadata)]


def read_data(path):
    suffix = Path(path).suffix.lower()
    if suffix in ('.mtc','.mta','.mtd'):
        from voltscope_dropview import read_dropview
        return read_dropview(path)
    if suffix in ('.ocw','.ici','.icw','.nox'):
        from voltscope_metrohm import read_gpes, read_nova
        return read_nova(path) if suffix == '.nox' else read_gpes(path)
    if suffix == '.cor':
        return read_corrware(path)
    if suffix in ('.idf', '.ids'):
        return read_ivium(path)
    return read_dta(path)


def export_csv(curves, path):
    """Export original columns/values/units with source and table provenance."""
    headers = []
    for curve in curves:
        for col, unit in zip(curve.columns, curve.units):
            label = f'{col} [{unit}]'
            if label not in headers:
                headers.append(label)
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Source file', 'Table'] + headers)
        for curve in curves:
            positions = {f'{col} [{unit}]': i for i, (col, unit) in enumerate(zip(curve.columns, curve.units))}
            for row in curve.rows:
                writer.writerow([Path(curve.source).name, curve.name] + [row[positions[h]] if h in positions else '' for h in headers])
