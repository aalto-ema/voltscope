"""BioLogic EC-Lab/BT-Lab ASCII tables and modular binary measurements.

MPR IDs/type table: cheminfo/biologic-converter (MIT), notice in third_party/.
Unknown binary layouts fail closed rather than estimating field widths.
"""
import json
import re
import struct
from pathlib import Path
from voltscope_import_utils import decode_text, table_curve


FLAGS = {1: ('mode', 3), 2: ('ox/red', 4), 3: ('error', 8),
         21: ('control changes', 16), 31: ('Ns changes', 32), 65: ('counter inc.', 128)}
TYPES = {'Float64': 'd', 'Float32': 'f', 'Uint16': 'H', 'Uint32': 'I',
         'Uint8': 'B', 'Int16': 'h', 'Int32': 'i'}


def read_biologic_text(path):
    lines = decode_text(Path(path).read_bytes()).splitlines()
    if not lines:
        raise ValueError('Empty BioLogic text file.')
    metadata = {'FORMAT': 'BioLogic ASCII'}
    if lines[0].strip() in ('EC-Lab ASCII FILE', 'BT-Lab ASCII FILE'):
        if len(lines) < 3:
            raise ValueError('Truncated BioLogic header.')
        match = re.fullmatch(r'Nb header lines\s*:\s*(\d+)\s*', lines[1])
        if not match or not 3 <= int(match[1]) <= len(lines):
            raise ValueError('Invalid BioLogic header-line count.')
        header = int(match[1]) - 1
        metadata['HEADER'] = '\n'.join(lines[:header])
        technique = next((line.strip() for line in lines[2:header] if line.strip()), '')
        metadata['TECHNIQUE'] = technique
        lower = technique.lower()
        metadata['TAG'] = ('CV' if 'voltammetry' in lower else 'CHRONOA' if 'chronoamper' in lower
                           else 'CHRONOP' if 'chronopot' in lower else 'EIS' if 'impedance' in lower else technique)
    else:
        header = 0
    labels = lines[header].strip().split('\t')
    # Header-only TXT exports have no vendor magic: require distinctive EC-Lab labels.
    if header == 0 and not ({'Ewe/V', '<Ewe>/V', 'Re(Z)/Ohm'} & set(labels)):
        raise ValueError('TXT is not a recognized BioLogic export (expected EC-Lab signal headers).')
    if len(labels) < 2 or any(not label for label in labels):
        raise ValueError('Invalid BioLogic column header.')
    rows = []
    for i, line in enumerate(lines[header + 1:], header + 2):
        if not line.strip():
            continue
        values = line.strip().split('\t')
        if len(values) != len(labels):
            raise ValueError(f'BioLogic column count mismatch at line {i}.')
        try:
            rows.append([float(v.replace(',', '.')) for v in values])
        except ValueError as exc:
            raise ValueError(f'Invalid BioLogic numeric value at line {i}.') from exc
    if not rows:
        raise ValueError('No BioLogic measurement rows.')
    if any(label.startswith('freq/') for label in labels):
        metadata['TAG'] = 'EIS'
    return [table_curve(path, Path(path).stem, labels, rows, metadata)]


def read_mpr(path):
    data = Path(path).read_bytes()
    if len(data) < 52 or not data.startswith(b'BIO-LOGIC MODULAR FILE\x1a'):
        raise ValueError('Not a BioLogic modular MPR file.')
    definitions = json.loads((Path(__file__).parent / 'third_party' / 'biologic_columns.json').read_text(encoding='utf-8'))
    offset, modules, curves = 52, [], []
    technique = None
    while offset < len(data):
        if data[offset:offset + 6] != b'MODULE' or offset + 57 > len(data):
            raise ValueError(f'Invalid/truncated BioLogic module at byte {offset}.')
        short, long, length, version, date = struct.unpack_from('<10s25sII8s', data, offset + 6)
        start, end = offset + 57, offset + 57 + length
        if end > len(data):
            raise ValueError('Truncated BioLogic module payload.')
        name = short.decode('ascii').strip(' \x00')
        modules.append({'name': name, 'description': long.decode('ascii').strip(),
                        'version': version, 'date': date.decode('ascii'), 'bytes': length})
        block = data[start:end]
        if name == 'VMP Set' and block:
            technique = block[0]
        if name == 'VMP data':
            if version not in (2, 3):
                raise ValueError(f'Unsupported BioLogic data-module version {version}.')
            if len(block) < 5:
                raise ValueError('Truncated BioLogic data dimensions.')
            count, width = struct.unpack_from('<IB', block)
            first = 405 if version == 2 else 406
            if not count or not width or 5 + width * 2 > first or len(block) < first:
                raise ValueError('Invalid BioLogic data dimensions.')
            ids = struct.unpack_from('<' + 'H' * width, block, 5)
            if len(set(ids)) != len(ids):
                raise ValueError('Repeated BioLogic binary column IDs are unsupported.')
            labels, layout, flags_position = [], [], None
            fmt = '<'
            for ident in ids:
                if ident in FLAGS:
                    if flags_position is None:
                        flags_position = len(layout)
                        fmt += 'B'
                        layout.append(('flags', None))
                    labels.append(FLAGS[ident][0] + ' [flag]')
                else:
                    if str(ident) not in definitions:
                        raise ValueError(f'Unsupported BioLogic column ID {ident}; cannot safely decode this binary layout. Export MPT instead.')
                    typ, title, unit = definitions[str(ident)]
                    if typ not in TYPES:
                        raise ValueError(f'Unsupported BioLogic storage type {typ}.')
                    fmt += TYPES[typ]
                    layout.append((ident, None))
                    labels.append(f'{title} [{unit}]' if unit else title)
            size = struct.calcsize(fmt)
            if first + size * count != len(block):
                raise ValueError('BioLogic data length does not match declared rows/columns; unsupported or truncated layout.')
            rows = []
            for packed in struct.iter_unpack(fmt, block[first:]):
                raw = {ident: value for (ident, _), value in zip(layout, packed)}
                row = []
                for ident in ids:
                    if ident in FLAGS:
                        mask = FLAGS[ident][1]
                        row.append((raw['flags'] & mask) >> ((mask & -mask).bit_length() - 1))
                    else:
                        row.append(raw[ident])
                rows.append(row)
            metadata = {'FORMAT': 'BioLogic MPR', 'DATE': date.decode('ascii'),
                        'COLUMN_IDS': ','.join(map(str, ids)), 'DATA_MODULE_VERSION': version}
            if 32 in ids:
                metadata['TAG'] = 'EIS'
            if 3 in ids and any(row[ids.index(3)] for row in rows):
                metadata['STATUS'] = 'Instrument error flag recorded; inspect error column.'
            curves.append(table_curve(path, f'{Path(path).stem} · data {len(curves) + 1}', labels, rows, metadata))
        offset = end
    if not curves:
        raise ValueError('No BioLogic measurement data module.')
    # Keep opaque settings/log/loop bytes as metadata rather than guessing offsets.
    for curve in curves:
        if technique is not None:
            curve.metadata['TECHNIQUE_ID'] = technique
            curve.metadata.setdefault('TAG', {6:'CV', 24:'CHRONOA', 25:'CHRONOP', 29:'EIS', 30:'EIS', 108:'CV'}.get(technique, str(technique)))
        curve.metadata['MODULES'] = json.dumps(modules)
        curve.metadata['SETTINGS_NOTE'] = 'Settings/log/loop modules retained as hex; cycle/step columns remain in stored row order.'
    offset = 52
    while offset < len(data):
        short, _, length, _, _ = struct.unpack_from('<10s25sII8s', data, offset + 6)
        if short.strip(b' \x00') != b'VMP data':
            key = f'MODULE_{offset}_{short.decode("ascii").strip()}_HEX'
            for curve in curves:
                curve.metadata[key] = data[offset + 57:offset + 57 + length].hex()
        offset += 57 + length
    return curves
