"""Read Zahner ISM arrays without sorting, trimming, or deriving impedance.

Layout reference: Zahner-elektrik/zahner-analysis-python (MIT).
Copyright 2024 Zahner-Elektrik GmbH & Co. KG; see third_party/Zahner-LICENSE.txt.
"""
import struct
from pathlib import Path
from voltscope_data import Curve


def read_ism(path):
    data = Path(path).read_bytes()
    if len(data) < 12:
        raise ValueError('Truncated Zahner ISM header.')
    version = int.from_bytes(data[:6], 'big', signed=True)
    count = int.from_bytes(data[6:12], 'big', signed=True) + 1
    # 4 double arrays (frequency, magnitude, phase, timestamp) + significance.
    end = 12 + count * 34
    if version not in (2, 0xfffffffe, 0xffffffff) or count <= 0 or end > len(data):
        raise ValueError('Unsupported or truncated Zahner ISM layout (expected supported classic ISM header).')
    arrays = [struct.unpack_from('>' + 'd' * count, data, 12 + i * count * 8) for i in range(4)]
    arrays.append(struct.unpack_from('>' + 'h' * count, data, 12 + count * 32))
    columns = ['freq', '|Z|', 'Phase(Z)', 'Timestamp', 'Significance']
    units = ['Hz', 'Ohm', 'rad', 's since 1980-01-01 (timezone unspecified)', 'unknown']
    metadata = {'FORMAT': 'Zahner ISM', 'TAG': 'EIS', 'VERSION': version,
                'UNIT_NOTE': 'Phase is stored in radians; all frequencies, including repeats, retained. No sign inversion or derived real/imaginary values.'}
    position = end

    def take(size):
        nonlocal position
        if size < 0 or position + size > len(data):
            raise ValueError('Truncated Zahner ISM metadata/acquisition arrays.')
        value = data[position:position + size]
        position += size
        return value

    if position < len(data):
        for key in ['DATE', 'SYSTEM', 'VOLTAGE', 'CURRENT', 'TEMPERATURE', 'TIME_WINDOW',
                    'COMMENT_1', 'COMMENT_2', 'COMMENT_3', 'COMMENT_4', 'AREA', 'SERIAL_QUANTITY']:
            length = int.from_bytes(take(2), 'big', signed=True)
            metadata[key] = take(length).decode('ascii').swapcase()
        flag = struct.unpack('>h', take(2))[0]
        parameters = struct.unpack('>32d', take(256))
        metadata['ACQUISITION_FLAG'] = flag
        metadata['K_VALUES'] = repr(parameters)
        if flag > 256 and int(parameters[27]) & 32768:
            values = list(struct.iter_unpack('>dd', take(count * 16)))
            arrays.extend([tuple(v[0] for v in values), tuple(v[1] for v in values)])
            columns.extend(['Vf', 'Im'])
            units.extend(['V', 'A'])
        if position < len(data):
            metadata['TRAILING_METADATA_HEX'] = data[position:].hex()
    return [Curve(str(path), Path(path).stem, columns, units,
                  [list(row) for row in zip(*arrays)], metadata)]
