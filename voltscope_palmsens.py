"""Data-only reader for PSTrace JSON PSSESSION files (UTF-8/UTF-16)."""
import json
from pathlib import Path
from voltscope_data import Curve
from voltscope_import_utils import decode_text, unique, metadata_json


UNIT_TYPES = {
    'Time': 's', 'Second': 's', 'Volt': 'V', 'MilliVolt': 'mV',
    'Ampere': 'A', 'MilliAmpere': 'mA', 'MicroAmpere': 'µA', 'NanoAmpere': 'nA',
    'Coulomb': 'C', 'MilliCoulomb': 'mC', 'MicroCoulomb': 'µC',
    'Ohm': 'Ohm', 'KiloOhm': 'kOhm', 'Hertz': 'Hz', 'Degree': 'deg',
    'Radian': 'rad', 'Farad': 'F', 'MicroFarad': 'µF',
}


def _lower(value):
    if isinstance(value, dict):
        return {key.lower(): _lower(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_lower(item) for item in value]
    return value


def _array(array):
    if not isinstance(array, dict) or not isinstance(array.get('datavalues'), list):
        raise ValueError('PalmSens array is missing DataValues.')
    typ = array.get('type', '').split('.')[-1]
    desc = str(array.get('description', ''))
    unit_object = array.get('unit', {})
    unit_type = str(unit_object.get('type', '')).split('.')[-1]
    # Unit.S is the base symbol, even when Type explicitly says MicroAmpere.
    unit = UNIT_TYPES.get(unit_type, unit_object.get('s') or 'unknown')
    quantity = (unit_object.get('q') or '').lower()
    column = ('T' if 'Time' in typ else 'Vf' if 'Potential' in typ else
              'Im' if 'Current' in typ else 'freq' if 'Frequenc' in typ else
              'freq' if desc.lower() == 'frequency' else
              'Vf' if quantity == 'potential' else 'Im' if quantity == 'current' else
              'Q' if 'Charge' in typ else desc or typ or 'Signal')
    if desc in ('Z', 'ZRe', 'ZIm', 'Phase'):
        column = {'Z': '|Z|', 'ZRe': 'Re(Z)', 'ZIm': '-Im(Z)' if quantity.startswith('-') else 'Im(Z)',
                  'Phase': '-Phase(Z)' if quantity.startswith('-') else 'Phase(Z)'}[desc]
    values = array['datavalues']
    if not values:
        return None
    if not all(isinstance(v, dict) and isinstance(v.get('v'), (int, float)) and
               not isinstance(v['v'], bool) for v in values):
        raise ValueError(f'Invalid PalmSens numeric array: {desc or typ}.')
    extras = list(dict.fromkeys(key for value in values for key in value if key != 'v'))
    if 'c' in extras and desc.lower() in ('idc', 'midc', 'iac'):
        unit = 'unknown'
        column = desc + ' raw'
    columns = [column] + [f'{column}.{key}' for key in extras]
    units = [unit] + ['unknown'] * len(extras)
    rows = [[value['v']] + [value.get(key, '') for key in extras] for value in values]
    return columns, units, rows, {'Description': desc, 'Type': typ,
                                 'Unit': unit_object, 'Properties': {k:v for k,v in array.items() if k != 'datavalues'}}


def _dataset(path, title, dataset, metadata):
    arrays = dataset.get('values')
    if not isinstance(arrays, list):
        raise ValueError(f'Unsupported PalmSens dataset layout: {title}.')
    groups, common_time, empty_arrays = {}, [], []
    for array in arrays:
        decoded = _array(array)
        if decoded is None:
            empty_arrays.append(str(array.get('description', array.get('type', 'Array'))))
            continue
        description = str(array.get('description', ''))
        if decoded[0][0] == 'T':
            common_time.append((description, decoded))
        else:
            # Explicit scan descriptions define scans; EIS descriptions name
            # signals instead, so retain their dataset grouping.
            key = description if description.lower().startswith(('scan', 'curve')) else 'Data'
            groups.setdefault(key, []).append(decoded)
    curves = []
    used_time = set()
    for name, signals in groups.items():
        # Some PSTrace versions store charge with one extra integration point.
        # Keep each length as its own table; never truncate or invent alignment.
        by_length = {}
        for signal in signals:
            by_length.setdefault(len(signal[2]), []).append(signal)
        for count, aligned in by_length.items():
            times = [(i, t) for i, (desc, t) in enumerate(common_time)
                     if (desc == name or (name == 'Data' and len(groups) == 1 and len(common_time) == 1)) and len(t[2]) == count]
            for i, time in reversed(times):
                aligned = [time] + aligned
                used_time.add(i)
            meta = dict(metadata)
            if len(by_length) > 1 or (common_time and not times):
                meta['STATUS'] = 'Stored arrays kept in separate tables where lengths or scan/time associations differ. Only explicitly associated matching time arrays included; no alignment inferred.'
            suffix = f' · {count} points' if len(by_length) > 1 else ''
            curves.append(_combine(path, f'{title} · {name}{suffix}', aligned, meta))
    for i, (description, time) in enumerate(common_time):
        if i not in used_time:
            curves.append(_combine(path, f'{title} · {description or "Time"}', [time], metadata))
    if empty_arrays:
        for curve in curves:
            curve.metadata['STATUS'] = (curve.metadata.get('STATUS', '') + ' Empty stored arrays skipped: ' + ', '.join(empty_arrays)).strip()
    return curves


def _combine(path, name, arrays, metadata):
    columns = unique([col for array in arrays for col in array[0]])
    units = [unit for array in arrays for unit in array[1]]
    rows = [sum((array[2][i] for array in arrays), []) for i in range(len(arrays[0][2]))]
    meta = dict(metadata, SOURCE_COLUMNS=' | '.join(columns),
                ARRAY_METADATA=metadata_json([a[3] for a in arrays]))
    if 'freq' in columns:
        meta['TAG'] = 'EIS'
    if any(name in columns for name in ('Idc raw', 'midc raw', 'Iac raw')):
        meta['UNIT_NOTE'] = 'Legacy EIS DC current range C retained; raw current unit unknown. No range conversion applied.'
    return Curve(str(path), name, columns, units, rows, meta)


def read_pssession(path):
    try:
        root = _lower(json.loads(decode_text(Path(path).read_bytes()).strip('\ufeff \t\r\n')))
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Invalid or truncated PalmSens JSON session.') from exc
    measurements = root.get('measurements') if isinstance(root, dict) else None
    if not isinstance(measurements, list) or not measurements:
        raise ValueError('PalmSens session has no Measurements list.')
    curves = []
    for index, measurement in enumerate(measurements, 1):
        if not isinstance(measurement, dict):
            raise ValueError(f'Invalid PalmSens measurement {index}.')
        title = f'{index}: {measurement.get("title", "Measurement")}'
        method = measurement.get('method', '')
        method_text = str(method).replace('\\r\\n', '\n')
        method_id = next((line.split('=', 1)[1].lower() for line in method_text.splitlines()
                          if line.startswith('METHOD_ID=')), '')
        metadata = {'FORMAT': 'PalmSens PSSESSION', 'TITLE': measurement.get('title', ''),
                    'PSTAT': measurement.get('deviceserial', ''), 'METHOD': method,
                    'TIMESTAMP_TICKS': measurement.get('timestamp', ''),
                    'UTC_TIMESTAMP_TICKS': measurement.get('utctimestamp', ''),
                    'CORE_VERSION': root.get('coreversion', ''),
                    'TAG': 'CV' if method_id in ('cv','lsv') else 'CHRONOA' if method_id in ('ad','ca') else 'CHRONOP' if method_id == 'cp' else method_id.upper(),
                    'MEASUREMENT_METADATA': metadata_json({k:v for k,v in measurement.items()
                        if k not in ('dataset','curves','eisdatalist')})}
        # Preserve stored raw datasets, not smoothed/baseline-corrected display curves.
        dataset = measurement.get('dataset')
        before = len(curves)
        if isinstance(dataset, dict) and dataset.get('values'):
            curves.extend(_dataset(path, title, dataset, metadata))
        else:
            # Some legacy sessions store DataArray objects as direct members.
            if isinstance(dataset, dict):
                direct = [v for v in dataset.values() if isinstance(v, dict) and 'datavalues' in v]
                if direct:
                    curves.extend(_dataset(path, title, {'values': direct}, metadata))
            if len(curves) == before:
                for i, curve in enumerate(measurement.get('curves', []), 1):
                    arrays = [_array(curve[key]) for key in ('xaxisdataarray','yaxisdataarray') if key in curve]
                    arrays = [a for a in arrays if a is not None]
                    if arrays:
                        if len({len(a[2]) for a in arrays}) != 1:
                            raise ValueError(f'PalmSens curve length mismatch: {title}.')
                        curves.append(_combine(path, f'{title} · curve {i}', arrays,
                                               dict(metadata, STATUS='Stored plot arrays only; raw dataset unavailable.')))
        # EIS scans may have their own datasets (e.g. multiple biases).
        seen = [dataset] if isinstance(dataset, dict) else []
        for eis_index, eis in enumerate(measurement.get('eisdatalist', []), 1):
            eis_dataset = eis.get('dataset') if isinstance(eis, dict) else None
            if isinstance(eis_dataset, dict) and eis_dataset not in seen:
                curves.extend(_dataset(path, f'{title} · EIS {eis_index}', eis_dataset,
                                       dict(metadata, TAG='EIS', EIS_METADATA=metadata_json({k:v for k,v in eis.items() if k != 'dataset'}))))
                seen.append(eis_dataset)
        if len(curves) == before:
            raise ValueError(f'No supported stored data in PalmSens measurement {index}; session import stopped to avoid silently skipping it.')
    return curves
