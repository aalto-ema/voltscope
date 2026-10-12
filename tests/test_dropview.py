import csv
import tempfile
import unittest
from pathlib import Path
from voltscope_data import read_data, export_csv


def curve_xml(tech='CV', name='Synthetic', i2='0,0', units=''):
    return f'<curve><name>{name}</name><channel>0</channel><technic id="{tech}"><commonUserParameters><parameter id="Srate">0.05</parameter></commonUserParameters></technic><points><time>0,1</time><potential>-0.5,0.5</potential><i1 {units}>1.25,-2.5</i1><i2>{i2}</i2></points></curve>'


def document(curves):
    return '<root><file device="STAT8000" version="2"/><title>Synthetic</title><curves>'+curves+'</curves></root>'

class DropViewChecks(unittest.TestCase):
    def test_multiple_curves_units_and_full_export(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'synthetic.mtc'
            path.write_text(document(curve_xml()+curve_xml('DPV','Pulse','1,2')))
            curves=read_data(path)
            self.assertEqual(len(curves),2)
            self.assertEqual(curves[0].columns,['T','Vf','I1','I2'])
            self.assertEqual(curves[0].units,['s','V','µA','µA'])
            self.assertEqual(curves[0].rows,[[0.,-.5,1.25,0.],[1.,.5,-2.5,0.]])
            self.assertEqual(curves[1].rows[0][-1],1.)
            self.assertEqual(curves[1].metadata['TAG'],'DPV')
            self.assertEqual(curves[0].metadata['commonUserParameters.Srate'],'0.05')
            out=Path(temp)/'out.csv';export_csv(curves,out)
            with out.open() as f: rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[0]['I1 [µA]'],'1.25')
            self.assertEqual(rows[-1]['I2 [µA]'],'2.0')
            path.write_text(document(curve_xml('AD',units='unit="µA"')))
            self.assertEqual(read_data(path)[0].units[2],'µA')

    def test_invalid_arrays_and_xml(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'invalid.mtd'
            for value in [document(curve_xml(i2='0')), document(curve_xml(i2='bad,0')), '<root>', '<!DOCTYPE root [<!ENTITY x "foo">]>'+document(curve_xml()), '<root><file/><curves/></root>']:
                path.write_text(value)
                with self.assertRaises(ValueError):read_data(path)
