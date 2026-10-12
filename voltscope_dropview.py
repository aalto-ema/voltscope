"""DropView XML import, preserving every stored point array."""
import xml.etree.ElementTree as ET
from pathlib import Path
from voltscope_data import Curve, number


def read_dropview(path):
    data = Path(path).read_bytes()
    # DropView documents need no DTDs or entities. Refuse them rather than
    # resolving declarations from untrusted measurement files.
    probe = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
        raise ValueError('DropView XML declarations with DTDs/entities are unsupported.')
    try: root = ET.fromstring(data)
    except ET.ParseError as exc: raise ValueError(f'Malformed DropView XML: {exc}') from exc
    if root.tag != 'root' or root.find('file') is None:
        raise ValueError('Not a supported DropView XML measurement file.')
    descriptor = root.find('file')
    curves = []
    for index, element in enumerate(root.findall('./curves/curve'), 1):
        points = element.find('points')
        if points is None or not len(points):
            raise ValueError(f'DropView curve {index} has no point arrays.')
        tech = element.find('technic')
        technique = tech.get('id', 'Unknown') if tech is not None else 'Unknown'
        metadata = {'FORMAT': 'DropView', 'TITLE': root.findtext('title', ''),
                    'PSTAT': descriptor.get('device', 'unknown'), 'FILE_VERSION': descriptor.get('version', 'unknown'),
                    'TECHNIQUE': technique, 'CHANNEL': element.findtext('channel', ''),
                    'TAG': {'CV': 'CV', 'AD': 'CHRONOA', 'DPV': 'DPV'}.get(technique, technique),
                    'STORED_COLOR': element.findtext('color', ''), 'STORED_SMOOTH': element.findtext('smooth', ''),
                    'UNIT_NOTE': 'Unlabelled i1/i2 arrays use µA, confirmed by the user for these DropView files. Explicit XML units take precedence; stored values are unchanged.'}
        if tech is not None:
            for group in tech:
                if group.tag.endswith('UserParameters'):
                    for parameter in group.iter('parameter'):
                        metadata[f'{group.tag}.{parameter.get("id", "unknown")}'] = parameter.text or ''
                elif group.tag in ('interval','numchannels','sensor','sample','value'):
                    metadata[group.tag] = group.text or ''
        columns, units, arrays = [], [], []
        for array in points:
            if array.tag in ('time','potential'):
                column, default_unit = {'time': ('T','s'), 'potential': ('Vf','V')}[array.tag]
            elif array.tag in ('i1','i2'):
                column, default_unit = array.tag.upper(), 'µA'
            else:
                column, default_unit = array.tag, 'unknown'
            unit = array.get('unit') or array.get('units') or default_unit
            if column in columns: raise ValueError(f'Duplicate DropView point array {array.tag}')
            tokens = (array.text or '').strip().split(',')
            values = [number(token.strip()) for token in tokens]
            if not values or any(v is None for v in values):
                raise ValueError(f'Invalid numeric values in DropView curve {index}, array {array.tag}')
            columns.append(column)
            units.append(unit)
            arrays.append(values)
        if len({len(values) for values in arrays}) != 1:
            raise ValueError(f'DropView curve {index} has unequal array lengths; data was not truncated.')
        metadata['SOURCE_COLUMNS'] = ' | '.join(array.tag for array in points)
        label = element.findtext('name') or f'Curve {index}'
        curves.append(Curve(str(path), label, columns, units, [list(row) for row in zip(*arrays)], metadata))
    if not curves: raise ValueError('DropView file contains no measurement curves.')
    return curves
