"""Generate wholly synthetic instrument-format demos; no experimental inputs.

Run from any directory with Python 3.10+: python tools/generate_examples.py
"""
import argparse
import math
from pathlib import Path
import struct

DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / 'outputs' / 'examples'


def cv(cycle=0):
    """Two linear sweeps at 50 mV/s with illustrative Gaussian peaks."""
    potentials = [-0.6 + i * 0.01 for i in range(121)]
    potentials += potentials[-2::-1]
    return [(i * 0.2, e, (1 + cycle * 0.08) * (
        25e-6 * math.exp(-((e - 0.22) / 0.10) ** 2) if i <= 120 else
        -20e-6 * math.exp(-((e + 0.05) / 0.12) ** 2)) +
        (2e-6 if i <= 120 else -2e-6)) for i, e in enumerate(potentials)]


def ca():
    # Explicit synthetic sampling times; light steps at 20/40/60/80 seconds.
    return [(i * 0.5, 0.5, 2e-6 + 18e-6 * math.exp(-i * 0.5 / 4) +
             (8e-6 if 20 <= i * 0.5 < 40 or 60 <= i * 0.5 < 80 else 0))
            for i in range(201)]


def _string(value):
    data = value.encode('utf-8')
    size = len(data)
    prefix = bytearray()
    while size >= 128:
        prefix.append((size & 127) | 128)
        size >>= 7
    return bytes(prefix) + bytes([size]) + data


def nova(rows):
    """Minimal data-only NRBF stream, without executable serialized objects."""
    result = bytearray(bytes.fromhex('0001000000ffffffff0100000000000000'))
    result.extend(b'\x0c' + struct.pack('<i', 1) + _string('Synthetic'))
    string_id = 1000

    def record(oid, name, fields):
        nonlocal string_id
        data = b'\x05' + struct.pack('<i', oid) + _string(name)
        data += struct.pack('<i', len(fields))
        data += b''.join(_string(key) for key, _, _ in fields)
        data += bytes(kind for _, kind, _ in fields) + struct.pack('<i', 1)
        for _, kind, value in fields:
            if kind == 1:
                string_id += 1
                data += b'\x06' + struct.pack('<i', string_id) + _string(value)
            else:
                data += b'\x09' + struct.pack('<i', value)
        return data

    result.extend(record(1, 'Procedure', [('_text', 1, 'SYNTHETIC CV demo'),
                                        ('_instrument', 1, 'Synthetic instrument')]))
    result.extend(record(2, 'Synthetic.CyclicVoltammetry',
                         [('FunctionHandler+_text', 1, 'Synthetic CV')]))
    for oid, (name, unit, index) in enumerate([
            ('EI_0.CalcCurrent', 'A', 2), ('EI_0.CalcPotential', 'V', 1),
            ('CalcTime', 's', 0)], 3):
        result.extend(record(oid, 'EcoChemie.Utils.Sequencer.CommandParameterDataArray', [
            ('_parameter', 2, oid + 10), ('CommandParameter+_parent', 2, 2),
            ('CommandParameter+_name', 1, name), ('CommandParameter+_unit', 1, unit)]))
        result.extend(b'\x0f' + struct.pack('<ii', oid + 10, len(rows)) + b'\x06')
        result.extend(struct.pack('<' + 'd' * len(rows), *(r[index] for r in rows)))
    return bytes(result) + b'\x0b'


def gamry(tag, curves):
    text = f'TAG\t{tag}\nTITLE\tLABEL\tSYNTHETIC demonstration\n'
    for n, rows in enumerate(curves, 1):
        text += f'CURVE{n}\tTABLE\t{len(rows)}\n\tPt\tT\tVf\tIm\n\t#\ts\tV vs. Ref.\tA\n'
        text += ''.join(f'\t{i}\t{t:.9g}\t{e:.9g}\t{current:.9g}\n'
                        for i, (t, e, current) in enumerate(rows))
    return text


def ivium(method, rows):
    technique = 'ChronoAmperometry' if method == 'Transients' else method
    values = [(e, current, e) if method == 'CyclicVoltammetry' else (t, current, e)
              for t, e, current in rows]
    return (f'QR=synthetic\r\nMethod={method}\r\nTechnique={technique}\r\n'
            'serialnumber=SYNTHETIC\r\nprimary_data    \r\x003\r\n'
            f'{len(values)}\r\n' + ''.join(' '.join(f'{x:.9g}' for x in row) + '\r\n'
                                                   for row in values)).encode('ascii')


def corrware(mode, rows):
    return ('CORRW ASCII\nCorrWare for Windows: Version synthetic\n' + mode +
            '\nBegin Experiment: ' + mode + '\nPstat Title: SYNTHETIC PAR demo\n'
            f'Data Points: {len(rows)}\nE(Volts)\tI(A/cm2)\tT(Seconds)\nEnd Comments\n' +
            ''.join(f'{e:.9g}\t{j:.9g}\t{t:.9g}\n' for t, e, j in rows))


def dropview(technique, rows):
    # Both stored current arrays are explicitly in microamperes.
    arrays = [('time', [r[0] for r in rows], 's'),
              ('potential', [r[1] for r in rows], 'V'),
              ('i1', [r[2] * 1e6 for r in rows], 'µA'),
              ('i2', [0.0 for _ in rows], 'µA')]
    return ('<?xml version="1.0" encoding="utf-8"?><root>'
            '<file device="SYNTHETIC" version="2"/><title>SYNTHETIC demo</title>'
            '<curves><curve><name>SYNTHETIC ' + technique + '</name><channel>0</channel>'
            '<technic id="' + technique + '"/><points>' + ''.join(
                f'<{name} unit="{unit}">' + ','.join(f'{v:.9g}' for v in values) + f'</{name}>'
                for name, values, unit in arrays) + '</points></curve></curves></root>')


def generate(destination=DEFAULT_DESTINATION):
    destination = Path(destination)
    files = {
        'gamry_cv_cycles.DTA': gamry('CV', [cv(i) for i in range(3)]),
        'gamry_ca_light_steps.DTA': gamry('CHRONOA', [ca()]),
        'ivium_cv_cycles.ids': b''.join(ivium('CyclicVoltammetry', cv(i)) for i in range(3)),
        'ivium_ca_light_steps.idf': ivium('Transients', ca()),
        'corrware_cv.cor': corrware('Cyclic Voltammogram', cv()),
        'corrware_potentiostatic.cor': corrware('Potentiostatic', ca()),
        'corrware_galvanostatic.cor': corrware('Galvanostatic', [
            (i, 0.2 + 0.001 * i + 0.08 * (1 - math.exp(-i / 8)), 1e-3)
            for i in range(201)]),
        'metrohm_nova_cv.nox': nova(cv()),
        'metrohm_gpes_cv.ocw': 'E / V,I / A\n' + ''.join(
            f'{e:.9g} {current:.9g}\n' for _, e, current in cv()),
        'metrohm_gpes_cv.ici': '[CV]\nxaxis.axtext=E / V\nyaxis.axtext=I / A\n',
        'metrohm_gpes_cv.icw': '200,40\n0\n01/01/2026\n12:00:00\n',
        'dropview_cv.mtc': dropview('CV', cv()),
        'dropview_amperometry.mta': dropview('AD', ca()),
        'dropview_pulse.mtd': dropview('DPV', [
            (i, -0.6 + i * 0.01, 12e-6 * math.exp(-((-0.6 + i * 0.01 - 0.1) / 0.08) ** 2))
            for i in range(121)]),
        'README.txt': 'SYNTHETIC VoltScope examples: no experimental measurements.\n'
        'Open these files using Open data or drag them into VoltScope.\n'
        'Keep the three metrohm_gpes_cv companion files together; open any one.\n'
        'CV: select Vf vs Im (I1 for DropView, J for Corrware).\n'
        'CA: select T vs Im/I1/J; galvanostatic: T vs Vf.\n'
        'Corrware values are synthetic current density in A/cm2, not current.\n'
        'All signals are illustrative formulas, not validated physical models.\n'
        'See docs/EXAMPLES.md for the catalog and suggested walkthrough.\n',
    }
    encoded = {name: value if isinstance(value, bytes) else value.encode('utf-8')
               for name, value in files.items()}
    # Check the entire batch before writing; never replace a modified file.
    for name, value in encoded.items():
        path = destination / name
        if path.exists() and path.read_bytes() != value:
            raise FileExistsError(f'Refusing to replace existing file: {path}')
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in encoded.items():
        path = destination / name
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(value)
    return [destination / name for name in files]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    paths = generate(args.destination)
    print(f'Created/verified {len(paths)} files in {args.destination.resolve()}')
