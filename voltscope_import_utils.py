"""Shared lossless import helpers, independent of the desktop UI."""
import json
import re
from pathlib import Path
from voltscope_data import Curve


def decode_text(data):
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1252')


def unique(names):
    result = []
    for name in names:
        candidate, i = name, 2
        while candidate in result:
            candidate = f'{name} ({i})'
            i += 1
        result.append(candidate)
    return result


def signal(label):
    """Map explicit headers only; preserve unfamiliar names and unknown units."""
    label = str(label).strip()
    match = re.fullmatch(r'(.*?)\s*\[([^\[\]]+)\]', label)
    if not match:
        match = re.fullmatch(r'(.*?)\s*\(([^()]+)\)', label)
        if match and match[2] not in ('V','mV','A','mA','µA','uA','nA','s','Hz','Ohm','ohm','Ω','deg','rad','A/cm2'):
            match = None
    if match:
        name, unit = match[1].strip(), match[2].strip()
    elif label in ('ox/red', 'Q charge/discharge'):
        name, unit = label, 'unknown'
    elif label.endswith('/V/mA'):
        name, unit = label[:-5], 'V/mA'
    elif '/' in label:
        name, unit = label.rsplit('/', 1)
    else:
        name, unit = label, 'unknown'
    if name.strip() == 'control':
        return ('Vset' if unit == 'V' else 'Iset' if unit == 'mA' else name.strip()), unit
    aliases = {'time': 'T', 'Time': 'T', 't': 'T', 'Ewe': 'Vf', '<Ewe>': 'Vf',
               'Potential': 'Vf', 'potential': 'Vf', 'I': 'Im', '<I>': 'Im',
               'Current': 'Im', 'current': 'Im', 'control_V': 'Vset',
               'freq': 'freq', 'Frequency': 'freq', 'frequency': 'freq'}
    return aliases.get(name.strip(), name.strip()), unit


def metadata_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def table_curve(path, name, labels, rows, metadata):
    pairs = [signal(label) for label in labels]
    columns = unique([p[0] for p in pairs])
    metadata = dict(metadata, SOURCE_COLUMNS=' | '.join(labels))
    return Curve(str(path), name, columns, [p[1] for p in pairs], rows, metadata)
