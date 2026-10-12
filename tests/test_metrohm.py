import unittest
import tempfile
import struct
from pathlib import Path
from voltscope_data import read_data, export_csv


def string(s):
    b=s.encode(); assert len(b)<128
    return bytes([len(b)])+b

def cls(oid,name,fields):
    # Synthetic NRBF class record: string/object members only.
    out=b'\x05'+struct.pack('<i',oid)+string(name)+struct.pack('<i',len(fields))
    out+=b''.join(string(k) for k,typ,value in fields)
    out+=bytes(typ for k,typ,value in fields)+struct.pack('<i',1)
    for k,typ,value in fields:
        out+= (b'\x06'+struct.pack('<i',1000+oid*10+len(out))+string(value)) if typ==1 else b'\x09'+struct.pack('<i',value)
    return out

def synthetic_nox():
    b=bytes.fromhex('0001000000ffffffff0100000000000000')
    b+=b'\x0c'+struct.pack('<i',1)+string('Synthetic')
    b+=cls(1,'Procedure',[('_text',1,'Synthetic CV'),('_instrument',1,'Synthetic instrument')])
    b+=cls(2,'Synthetic.CyclicVoltammetry',[('FunctionHandler+_text',1,'Synthetic scan')])
    for i,(name,unit,values) in enumerate([('EI_0.CalcCurrent','A',[1e-6,2e-6]),('EI_0.CalcPotential','V',[-.5,.5]),('CalcTime','s',[0.,1.])],3):
        b+=cls(i,'EcoChemie.Utils.Sequencer.CommandParameterDataArray',[('_parameter',2,i+10),('CommandParameter+_parent',2,2),('CommandParameter+_name',1,name),('CommandParameter+_unit',1,unit)])
        b+=b'\x0f'+struct.pack('<ii',i+10,len(values))+b'\x06'+struct.pack('<'+'d'*len(values),*values)
    return b+b'\x0b'

class MetrohmChecks(unittest.TestCase):
    def test_nova_stored_signals_and_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'synthetic.nox'
            path.write_bytes(synthetic_nox())
            curves=read_data(path)
            self.assertEqual(len(curves),1)
            self.assertEqual(curves[0].rows,[[1e-6,-.5,0.],[2e-6,.5,1.]])
            self.assertEqual(curves[0].units,['A','V','s'])
            path.write_bytes(synthetic_nox()+synthetic_nox())
            self.assertEqual(len(read_data(path)),2)
            path.write_bytes(synthetic_nox()[:-8])
            with self.assertRaises(ValueError): read_data(path)

    def test_gpes_companions_and_explicit_units(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)/'synthetic'
            ocw=base.with_suffix('.ocw');ici=base.with_suffix('.ici');icw=base.with_suffix('.icw')
            ocw.write_text(' \n,\n-.5 1e-6\n.5 -2e-6\n')
            ici.write_text('[CV]\nxaxis.axtext=E / V\nyaxis.axtext=I / A\n')
            icw.write_text('200,40\n0\n01/01/2026\n12:00:00\n')
            for path in [ocw,ici,icw]:
                curve=read_data(path)[0]
                self.assertEqual(curve.source,str(ocw))
                self.assertEqual(curve.columns,['Vf','Im'])
                self.assertEqual(curve.units,['V','A'])
                self.assertEqual(curve.rows,[[-.5,1e-6],[.5,-2e-6]])
                self.assertEqual(curve.metadata['DATE'],'01/01/2026')
                out=Path(temp)/'out.csv';export_csv([curve],out)
                self.assertIn('Im [A]',out.read_text())
            ici.unlink()
            curve=read_data(ocw)[0]
            self.assertEqual(curve.units,['unknown','unknown'])
            ocw.unlink()
            with self.assertRaises(ValueError): read_data(icw)
            ocw.write_text('E / V,I / A\n.5 invalid\n')
            with self.assertRaises(ValueError): read_data(ocw)
