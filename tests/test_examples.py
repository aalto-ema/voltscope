"""Verify the user-facing synthetic demo pack with the actual readers."""
import csv
import tempfile
import unittest
from pathlib import Path

from tools.generate_examples import generate
from voltscope_data import read_data, export_csv


class ExampleChecks(unittest.TestCase):
    def test_catalog_import_and_export(self):
        expected = {
            'gamry_cv_cycles.DTA': (3, 241, 'Im', 'A'),
            'gamry_ca_light_steps.DTA': (1, 201, 'Im', 'A'),
            'ivium_cv_cycles.ids': (3, 241, 'Im', 'A'),
            'ivium_ca_light_steps.idf': (1, 201, 'Im', 'A'),
            'corrware_cv.cor': (1, 241, 'J', 'A/cm2'),
            'corrware_potentiostatic.cor': (1, 201, 'J', 'A/cm2'),
            'corrware_galvanostatic.cor': (1, 201, 'J', 'A/cm2'),
            'metrohm_nova_cv.nox': (1, 241, 'Im', 'A'),
            'metrohm_gpes_cv.ocw': (1, 241, 'Im', 'A'),
            'metrohm_gpes_cv.ici': (1, 241, 'Im', 'A'),
            'metrohm_gpes_cv.icw': (1, 241, 'Im', 'A'),
            'dropview_cv.mtc': (1, 241, 'I1', 'µA'),
            'dropview_amperometry.mta': (1, 201, 'I1', 'µA'),
            'dropview_pulse.mtd': (1, 121, 'I1', 'µA'),
        }
        with tempfile.TemporaryDirectory() as folder:
            paths = generate(folder)
            all_curves = []
            for path in paths:
                if path.suffix == '.txt':
                    continue
                with self.subTest(file=path.name):
                    curves = read_data(path)
                    count, points, current, unit = expected[path.name]
                    self.assertEqual(len(curves), count)
                    for curve in curves:
                        self.assertEqual(len(curve.rows), points)
                        self.assertEqual(curve.units[curve.columns.index(current)], unit)
                    all_curves.extend(curves)
            ca = read_data(Path(folder) / 'ivium_ca_light_steps.idf')[0]
            self.assertEqual(ca.columns, ['T', 'Im', 'Vf'])
            self.assertEqual(ca.rows[0], [0., 20e-6, .5])
            cv = read_data(Path(folder) / 'gamry_cv_cycles.DTA')[0]
            e = [row[cv.columns.index('Vf')] for row in cv.rows]
            self.assertEqual((e[0], e[120], e[-1]), (-.6, .6, -.6))
            out = Path(folder) / 'mixed.csv'
            export_csv(all_curves, out)
            with out.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), sum(len(c.rows) for c in all_curves))
            self.assertIn('I1 [µA]', rows[0])
            self.assertIn('J [A/cm2]', rows[0])
            self.assertEqual(rows[0]['Im [A]'], str(cv.rows[0][3]))
            self.assertEqual(rows[0]['I1 [µA]'], '')

    def test_repeatable_and_protects_modified_files(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = generate(folder)
            originals = {p: p.read_bytes() for p in paths}
            generate(folder)
            self.assertEqual(originals, {p: p.read_bytes() for p in paths})
            changed = paths[0]
            changed.write_bytes(b'user data')
            with self.assertRaises(FileExistsError):
                generate(folder)
            self.assertEqual(changed.read_bytes(), b'user data')
