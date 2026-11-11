"""Independent synthetic fixtures for public-data format support; no real data."""
import csv
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from voltscope_data import read_data, export_csv, SUPPORTED_SUFFIXES


def mpr(version=2, ident=8):
    # 2 records: shared flags byte, measured time/E, current and control voltage.
    ids = [1, 2, 3, 4, 6, ident, 19]
    block = struct.pack('<IB', 2, len(ids)) + struct.pack('<7H', *ids)
    block = block.ljust(405 if version == 2 else 406, b'\0')
    block += struct.pack('<Bdfff', 6, 10., -.5, .25, -.4)
    block += struct.pack('<Bdfff', 10, 11., .5, -.125, .4)

    def module(name, body, version=0):
        return b'MODULE' + struct.pack('<10s25sII8s', name, name, len(body), version, b'01/01/26') + body
    return (b'BIO-LOGIC MODULAR FILE\x1a'.ljust(52, b' ') +
            module(b'VMP Set', b'\x06settings') + module(b'VMP data', block, version))


def ism():
    # Deliberately repeated frequencies in acquisition order.
    data = (0xffffffff).to_bytes(6, 'big') + (2).to_bytes(6, 'big')
    for values in [(10., 1., 10.), (5., 6., 7.), (-.2, -.3, -.4), (100., 101., 102.)]:
        data += struct.pack('>3d', *values)
    return data + struct.pack('>3h', 1000, 999, 998)


def array(typ, desc, unit, values, extra=False):
    return {'Type': 'PalmSens.Data.' + typ, 'Description': desc,
            'Unit': {'Type': 'PalmSens.Units.' + unit, 'S': 'A' if unit == 'MicroAmpere' else unit},
            'DataValues': [{'V': value, **({'C': 2, 'S': 0} if extra else {})} for value in values]}


def session(arrays, **kwargs):
    return {'CoreVersion': 'synthetic', 'Measurements': [{'Title': 'Synthetic',
            'Method': 'METHOD_ID=cv\r\n', 'DataSet': {'Values': arrays}, **kwargs}]}


class Imports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def write(self, name, content):
        p = self.base / name
        p.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return p

    def test_biologic_text_units_and_rejected_unrelated_txt(self):
        text = ('EC-Lab ASCII FILE\nNb header lines : 4\nCyclic Voltammetry\n'
                'time/s\tEwe/V\tcontrol/V\t<I>/mA\tox/red\tcycle number\n'
                '0\t-0,5\t-0,6\t0,25\t1\t1\n1\t0,5\t0,6\t-0,125\t0\t2\n')
        p = self.write('a.mpt', text)
        c = read_data(p)[0]
        self.assertEqual(c.columns, ['T','Vf','Vset','Im','ox/red','cycle number'])
        self.assertEqual(c.units[:4], ['s','V','V','mA'])
        self.assertEqual(c.rows[0][:4], [0.,-.5,-.6,.25])
        self.assertEqual(c.metadata['TAG'], 'CV')
        txt = self.write('export.txt', '\n'.join(text.splitlines()[3:]))
        self.assertEqual(read_data(txt)[0].rows, c.rows)
        for invalid in ['notes\nHello', text.replace(' : 4', ' : 100'), text.replace('0,25','bad'), text.replace('\t0,25','')]:
            p.write_text(invalid)
            with self.assertRaises(ValueError): read_data(p)

    def test_mpr_flags_versions_values_and_fail_closed(self):
        p = self.base / 'a.mpr'
        for version in (2,3):
            p.write_bytes(mpr(version))
            c = read_data(p)[0]
            self.assertEqual(c.columns, ['mode','ox/red','error','T','Vf','Im','Vset'])
            self.assertEqual(c.rows[0], [2,1,0,10.,-.5,.25,struct.unpack('<f',struct.pack('<f',-.4))[0]])
            self.assertEqual(c.units[5], 'mA')
            self.assertEqual(c.metadata['TAG'], 'CV')
            self.assertIn('error flag', c.metadata['STATUS'])
            self.assertTrue(any(key.endswith('_HEX') for key in c.metadata))
        for content in [mpr()[:-1], mpr(9), mpr(2,999), b'bad', mpr()+b'junk']:
            p.write_bytes(content)
            with self.assertRaises(ValueError): read_data(p)

    def test_palmsens_encoding_boundaries_units_status_and_unequal_arrays(self):
        data = session([
            array('DataArrayTime','time','Time',[0,1]),
            array('DataArrayPotentials','scan1','Volt',[-.5,.5]),
            array('DataArrayCurrents','scan1','MicroAmpere',[1.25,-2.5],True),
            array('DataArrayCharge','scan1','MicroCoulomb',[0,1,2]),
            array('DataArrayPotentials','scan2','Volt',[.5,-.5]),
            array('DataArrayCurrents','scan2','MicroAmpere',[3.,-4.],True),
        ])
        p = self.base / 'a.pssession'
        for encoding in ['utf-8-sig','utf-16']:
            p.write_bytes((json.dumps(data)+'\ufeff').encode(encoding))
            curves=read_data(p)
            self.assertEqual(len(curves),4)  # two scans, unaligned charge, independent time
            c=curves[0]
            self.assertEqual(c.columns,['Vf','Im','Im.c','Im.s'])
            self.assertEqual(c.units[1],'µA')
            self.assertEqual(c.rows[0],[-.5,1.25,2,0])
            self.assertEqual(curves[1].rows,[[0],[1],[2]])
            self.assertIn('separate tables',curves[0].metadata['STATUS'])
            self.assertNotIn('T',c.columns)  # no time-axis association inferred
            out=self.base/'out.csv';export_csv(curves,out)
            with out.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),9)
            self.assertEqual(rows[0]['Im [µA]'],'1.25')
        for content in ['{}','{"Measurements":[',json.dumps(session([{'DataValues':[{'V':'bad'}]}]))]:
            p.write_text(content)
            with self.assertRaises(ValueError):read_data(p)

    def test_palmsens_eis_units_and_legacy_case(self):
        a=array('DataArray','Frequency','Hertz',[100,10])
        b=array('DataArray','Z','Ohm',[12,13])
        dc=array('DataArrayCurrents','Idc','MicroAmpere',[1,2],True)
        data=session([a,b,dc])
        # Exercise older lowercase key spelling.
        text=json.dumps(data)
        for key in ['Measurements','DataSet','Values','DataValues','Type','Description','Unit','V','C','S']:
            text=text.replace('"'+key+'":','"'+key.lower()+'":')
        c=read_data(self.write('eis.pssession',text))[0]
        self.assertEqual(c.metadata['TAG'],'EIS')
        self.assertEqual(c.columns[:2],['freq','|Z|'])
        self.assertEqual(c.units[2],'unknown')
        self.assertIn('range',c.metadata['UNIT_NOTE'])

    def test_ism_order_radians_metadata_acq_and_truncation(self):
        p=self.write('a.ism',ism())
        c=read_data(p)[0]
        self.assertEqual([r[0] for r in c.rows],[10.,1.,10.])
        self.assertEqual(c.rows[0],[10.,5.,-.2,100.,1000])
        self.assertEqual(c.units[2],'rad')
        metadata=b''
        for s in ['010126','Synthetic','','','','','','','','','','']:
            b=s.swapcase().encode('ascii');metadata+=struct.pack('>h',len(b))+b
        params=[0.]*32;params[27]=32768
        metadata+=struct.pack('>h',257)+struct.pack('>32d',*params)+struct.pack('>6d',.1,1e-6,.2,2e-6,.3,3e-6)
        p.write_bytes(ism()+metadata)
        c=read_data(p)[0]
        self.assertEqual(c.metadata['SYSTEM'],'Synthetic')
        self.assertEqual(c.rows[0][-2:],[.1,1e-6])
        for value in [ism()[:-1],ism()+b'\0',ism()+metadata[:-1],b'bad']:
            p.write_bytes(value)
            with self.assertRaises(ValueError):read_data(p)

    def test_csv_xlsx_mixed_export_and_formula_rejection(self):
        p=self.write('a.csv','T [s];Im [µA];Status\n0;1,25;ok\n1;-2,5;aborted\n')
        c=read_data(p)[0]
        self.assertEqual(c.rows,[[0.,1.25,'ok'],[1.,-2.5,'aborted']])
        self.assertEqual(c.units,['s','µA','unknown'])
        from openpyxl import Workbook
        w=Workbook();s=w.active;s.title='CV'
        s.append([None,'Sample']);s.append(['V','µA']);s.append([-.5,2.]);s.append([.5,-3.])
        w.create_sheet('Empty');x=self.base/'a.xlsx';w.save(x);w.close()
        xc=read_data(x)[0]
        self.assertEqual(xc.columns,['Column 1','Sample'])
        self.assertEqual(xc.units,['V','µA'])
        self.assertEqual(len(xc.rows),2)
        self.assertIn('Empty',xc.metadata['STATUS'])
        dest=self.base/'mixed.csv';export_csv([c,xc],dest)
        with dest.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]['Sample [µA]'],'')
        s.cell(3,2,'=1+2');w.save(x)
        with self.assertRaises(ValueError):read_data(x)

    def test_ui_new_file_open_axes_and_export(self):
        from PySide6.QtWidgets import QApplication, QFileDialog
        from PySide6.QtTest import QTest
        from voltscope_ui import Viewer
        app=QApplication.instance() or QApplication([])
        p=self.write('a.ism',ism());window=Viewer();window.show()
        try:
            with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(p)],'')) as dialog:
                window.open()
            deadline=time.monotonic()+5
            while window.importer is not None and time.monotonic()<deadline:
                app.processEvents();QTest.qWait(10)
            self.assertIsNone(window.importer)
            self.assertIn('*.pssession',dialog.call_args.args[-1])
            self.assertEqual(window.xbox.currentText(),'freq')
            self.assertEqual(window.ybox.currentText(),'|Z|')
            self.assertEqual(len(window.plot.series),1)
            self.assertFalse(window.plot.grab().isNull())
            out=self.base/'ui.csv'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(out),'')):
                window.export()
            self.assertIn('Phase(Z) [rad]',out.read_text())
            window.clear()
            generic = self.write('wide.csv', 'Axis [V],Sample [µA]\n-0.5,1.25\n0.5,-2.5\n')
            window.load([str(generic)])
            deadline=time.monotonic()+5
            while window.importer is not None and time.monotonic()<deadline:
                app.processEvents();QTest.qWait(10)
            self.assertIsNone(window.importer)
            self.assertEqual(window.xbox.currentText(),'Axis')
            self.assertEqual(window.ybox.currentText(),'Sample')
            self.assertEqual(window.plot.series[0][1][0],(-.5,1.25))
            self.assertTrue({'.mpr','.mpt','.txt','.pssession','.ism','.csv','.xlsx'} <= set(SUPPORTED_SUFFIXES))
        finally:
            if window.importer:
                window.importer.wait();app.processEvents()
            window.close();window.deleteLater();app.processEvents()
